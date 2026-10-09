/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useMemo, useState } from 'react';
import { onAuthStateChanged, User } from 'firebase/auth';
import {
  collection,
  doc,
  getDoc,
  onSnapshot,
  query,
  runTransaction,
  serverTimestamp,
  where,
  writeBatch,
} from 'firebase/firestore';
import {
  Film,
  MapPin,
  Search,
  Ticket,
  User as UserIcon,
  Calendar,
  Clock,
  CheckCircle2,
  AlertCircle,
  ArrowLeft,
  SlidersHorizontal,
} from 'lucide-react';
import {
  auth,
  db,
  handleFirestoreError,
  OperationType,
  sanitizeId,
  signInAndSyncProfile,
  signOutUser,
  VALIDATION_RULES,
} from './lib/firebase';
import {
  AUDITORIUM_ROWS,
  AVAILABLE_DATES,
  getAuditoriumSeats,
  getSeatPrice,
  HERO_BANNER_IMAGE,
  MovieItem,
  MOVIES_CATALOG,
  SHOWTIMES_CATALOG,
  ShowtimeItem,
  THEATRES_CATALOG,
} from './data/catalog';
import { BookingRecord, TicketModal } from './components/TicketModal';
import { DjangoBlueprintPanel } from './components/DjangoBlueprintPanel';

type ActiveTab = 'movies' | 'theatres' | 'bookings' | 'profile' | 'architecture';

export default function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<ActiveTab>('movies');

  // Search, Filters & Pagination
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedGenre, setSelectedGenre] = useState<string>('all');
  const [selectedLanguage, setSelectedLanguage] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<'all' | 'now_showing' | 'coming_soon'>('all');
  const [sortBy, setSortBy] = useState<'release' | 'title' | 'duration'>('release');
  const [selectedCity, setSelectedCity] = useState<string>('All Cities');

  // Booking Flow State
  const [selectedMovie, setSelectedMovie] = useState<MovieItem | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>(AVAILABLE_DATES[0].date);
  const [selectedShow, setSelectedShow] = useState<ShowtimeItem | null>(null);
  const [liveBookedSeats, setLiveBookedSeats] = useState<string[]>([]);
  const [selectedSeats, setSelectedSeats] = useState<string[]>([]);
  const [isBookingProcessing, setIsBookingProcessing] = useState<boolean>(false);

  // User Bookings & Modal State
  const [userBookings, setUserBookings] = useState<BookingRecord[]>([]);
  const [activeTicketModal, setActiveTicketModal] = useState<BookingRecord | null>(null);

  // User Profile State
  const [profileDisplayName, setProfileDisplayName] = useState<string>('');
  const [profileCity, setProfileCity] = useState<string>('Mumbai');
  const [profilePhone, setProfilePhone] = useState<string>('');
  const [profileSaving, setProfileSaving] = useState<boolean>(false);

  // Toast Notification
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Image error fallback tracking
  const [brokenImages, setBrokenImages] = useState<Record<string, boolean>>({});

  const showToast = (type: 'success' | 'error', message: string) => {
    setToast({ type, message });
    setTimeout(() => {
      setToast((prev) => (prev?.message === message ? null : prev));
    }, 4500);
  };

  // Track Firebase Authentication State
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      setCurrentUser(user);
      setAuthReady(true);
      if (user) {
        const uid = sanitizeId(user.uid);
        try {
          const userSnap = await getDoc(doc(db, 'users', uid));
          if (userSnap.exists()) {
            const data = userSnap.data();
            setProfileDisplayName(data.displayName || user.displayName || '');
            setProfileCity(data.preferredCity || 'Mumbai');
          } else {
            setProfileDisplayName(user.displayName || user.email?.split('@')[0] || 'Cinema Guest');
          }
          const privSnap = await getDoc(doc(db, 'users', uid, 'private', 'info'));
          if (privSnap.exists()) {
            setProfilePhone(privSnap.data().phone || '');
          }
        } catch (err) {
          // Profile may not be initialized yet if sign-in batch is in flight
          console.warn('Profile load deferred:', err);
        }
      } else {
        setUserBookings([]);
      }
    });
    return () => unsubscribe();
  }, []);

  // Subscribe to User's Bookings when authenticated
  useEffect(() => {
    if (!authReady || !currentUser) {
      setUserBookings([]);
      return;
    }
    const uid = sanitizeId(currentUser.uid);
    const bookingsQuery = query(collection(db, 'bookings'), where('userId', '==', uid));
    const unsubscribe = onSnapshot(
      bookingsQuery,
      (snapshot) => {
        const records: BookingRecord[] = [];
        snapshot.forEach((docSnap) => {
          const d = docSnap.data();
          records.push({
            bookingRef: d.bookingRef,
            userId: d.userId,
            showId: d.showId,
            movieId: d.movieId,
            movieTitle: d.movieTitle,
            theatreName: d.theatreName,
            screenName: d.screenName,
            showDate: d.showDate,
            startTime: d.startTime,
            seats: Array.isArray(d.seats) ? d.seats : [],
            subtotalAmount: Number(d.subtotalAmount || 0),
            convenienceFee: Number(d.convenienceFee || 0),
            totalAmount: Number(d.totalAmount || 0),
            status: d.status,
            paymentStatus: d.paymentStatus,
            paymentTxnId: d.paymentTxnId,
          });
        });
        records.sort((a, b) => b.bookingRef.localeCompare(a.bookingRef));
        setUserBookings(records);
      },
      (error) => {
        handleFirestoreError(error, OperationType.LIST, 'bookings');
      }
    );
    return () => unsubscribe();
  }, [authReady, currentUser]);

  // Subscribe to Real-Time Show Seat Occupancy when a Show is selected
  useEffect(() => {
    if (!selectedShow) {
      setLiveBookedSeats([]);
      setSelectedSeats([]);
      return;
    }
    setSelectedSeats([]);
    const showDocRef = doc(db, 'shows', selectedShow.id);
    const unsubscribe = onSnapshot(
      showDocRef,
      (docSnap) => {
        if (docSnap.exists()) {
          const data = docSnap.data();
          const firestoreSeats = Array.isArray(data.bookedSeats) ? data.bookedSeats : [];
          const merged = Array.from(new Set([...selectedShow.initialBookedSeats, ...firestoreSeats]));
          setLiveBookedSeats(merged);
        } else {
          setLiveBookedSeats(selectedShow.initialBookedSeats);
        }
      },
      (error) => {
        handleFirestoreError(error, OperationType.GET, `shows/${selectedShow.id}`);
      }
    );
    return () => unsubscribe();
  }, [selectedShow]);

  // Filtered and Sorted Movies
  const filteredMovies = useMemo(() => {
    return MOVIES_CATALOG.filter((movie) => {
      const q = searchQuery.trim().toLowerCase();
      if (
        q &&
        !movie.title.toLowerCase().includes(q) &&
        !movie.director.toLowerCase().includes(q) &&
        !movie.cast.toLowerCase().includes(q)
      ) {
        return false;
      }
      if (selectedGenre !== 'all' && movie.genre !== selectedGenre) return false;
      if (selectedLanguage !== 'all' && movie.language !== selectedLanguage) return false;
      if (selectedStatus !== 'all' && movie.status !== selectedStatus) return false;
      return true;
    }).sort((a, b) => {
      if (sortBy === 'title') return a.title.localeCompare(b.title);
      if (sortBy === 'duration') return a.durationMinutes - b.durationMinutes;
      return b.releaseDate.localeCompare(a.releaseDate);
    });
  }, [searchQuery, selectedGenre, selectedLanguage, selectedStatus, sortBy]);

  // Showtimes for Selected Movie
  const movieShowtimes = useMemo(() => {
    if (!selectedMovie) return [];
    return SHOWTIMES_CATALOG.filter((sh) => {
      if (sh.movieId !== selectedMovie.id) return false;
      if (selectedCity !== 'All Cities' && sh.city !== selectedCity) return false;
      if (selectedDate && sh.showDate !== selectedDate) return false;
      return true;
    });
  }, [selectedMovie, selectedCity, selectedDate]);

  const auditoriumSeats = useMemo(() => getAuditoriumSeats(), []);

  // Pricing Breakdown for Selected Seats
  const pricingSummary = useMemo(() => {
    if (!selectedShow || selectedSeats.length === 0) {
      return { subtotal: 0, convenienceFee: 0, total: 0 };
    }
    let subtotal = 0;
    for (const code of selectedSeats) {
      const def = auditoriumSeats.find((s) => s.code === code);
      if (def) {
        subtotal += getSeatPrice(selectedShow, def.tier);
      }
    }
    const convenienceFee = Math.round(subtotal * 0.08 * 100) / 100;
    const total = Math.round((subtotal + convenienceFee) * 100) / 100;
    return { subtotal, convenienceFee, total };
  }, [selectedShow, selectedSeats, auditoriumSeats]);

  const handleToggleSeat = (seatCode: string) => {
    if (liveBookedSeats.includes(seatCode)) return;
    setSelectedSeats((prev) => {
      if (prev.includes(seatCode)) {
        return prev.filter((c) => c !== seatCode);
      }
      if (prev.length >= VALIDATION_RULES.MAX_SEATS_PER_BOOKING) {
        showToast('error', 'Maximum 10 seats can be reserved in a single booking.');
        return prev;
      }
      return [...prev, seatCode];
    });
  };

  const handleSignIn = async () => {
    try {
      await signInAndSyncProfile();
      showToast('success', 'Signed in to MyBookShow.');
    } catch (err) {
      showToast('error', 'Sign-in could not be completed. Please try again.');
    }
  };

  const handleCreateBooking = async () => {
    if (!selectedShow || !selectedMovie || selectedSeats.length === 0) return;

    let user = currentUser;
    if (!user) {
      try {
        user = await signInAndSyncProfile();
      } catch {
        showToast('error', 'Please sign in with Google to reserve seats.');
        return;
      }
    }

    setIsBookingProcessing(true);
    const uid = sanitizeId(user.uid);
    const randomSuffix = Math.random().toString(36).substring(2, 8).toUpperCase();
    const bookingRef = sanitizeId(`MBS-${Date.now().toString(36).toUpperCase()}-${randomSuffix}`, 32);
    const showRef = doc(db, 'shows', selectedShow.id);
    const bookingDocRef = doc(db, 'bookings', bookingRef);

    try {
      const createdRecord: BookingRecord = {
        bookingRef,
        userId: uid,
        showId: sanitizeId(selectedShow.id),
        movieId: sanitizeId(selectedMovie.id),
        movieTitle: selectedMovie.title.slice(0, VALIDATION_RULES.MOVIE_TITLE_MAX),
        theatreName: selectedShow.theatreName.slice(0, VALIDATION_RULES.THEATRE_NAME_MAX),
        screenName: selectedShow.screenName.slice(0, VALIDATION_RULES.SCREEN_NAME_MAX),
        showDate: selectedShow.showDate,
        startTime: selectedShow.startTime,
        seats: [...selectedSeats].slice(0, VALIDATION_RULES.MAX_SEATS_PER_BOOKING),
        subtotalAmount: pricingSummary.subtotal,
        convenienceFee: pricingSummary.convenienceFee,
        totalAmount: pricingSummary.total,
        status: 'pending_payment',
        paymentStatus: 'pending',
        paymentTxnId: `ORD-${randomSuffix}`,
      };

      await runTransaction(db, async (transaction) => {
        const showSnap = await transaction.get(showRef);
        const existingFirestoreSeats: string[] = showSnap.exists()
          ? Array.isArray(showSnap.data().bookedSeats)
            ? showSnap.data().bookedSeats
            : []
          : [];
        const allCurrentlyBooked = new Set([
          ...selectedShow.initialBookedSeats,
          ...existingFirestoreSeats,
        ]);

        for (const seatCode of createdRecord.seats) {
          if (allCurrentlyBooked.has(seatCode)) {
            throw new Error(`SEAT_CONFLICT:${seatCode}`);
          }
          allCurrentlyBooked.add(seatCode);
        }

        const updatedSeatList = Array.from(allCurrentlyBooked).slice(
          0,
          VALIDATION_RULES.MAX_BOOKED_SEATS_PER_SHOW
        );

        if (!showSnap.exists()) {
          transaction.set(showRef, {
            showId: sanitizeId(selectedShow.id),
            movieId: sanitizeId(selectedMovie.id),
            theatreId: sanitizeId(selectedShow.theatreId),
            screenName: selectedShow.screenName.slice(0, VALIDATION_RULES.SCREEN_NAME_MAX),
            showDate: selectedShow.showDate,
            startTime: selectedShow.startTime,
            bookedSeats: updatedSeatList,
            lastBookedBy: uid,
            createdAt: serverTimestamp(),
            updatedAt: serverTimestamp(),
          });
        } else {
          transaction.update(showRef, {
            bookedSeats: updatedSeatList,
            lastBookedBy: uid,
            updatedAt: serverTimestamp(),
          });
        }

        transaction.set(bookingDocRef, {
          ...createdRecord,
          createdAt: serverTimestamp(),
          updatedAt: serverTimestamp(),
        });
      });

      setSelectedSeats([]);
      setActiveTicketModal(createdRecord);
      showToast(
        'success',
        `Seats locked under reference ${bookingRef}. Complete payment verification to confirm.`
      );
    } catch (error) {
      if (error instanceof Error && error.message.startsWith('SEAT_CONFLICT:')) {
        const seat = error.message.split(':')[1];
        showToast('error', `Seat ${seat} was just reserved by another guest. Please select another seat.`);
      } else {
        handleFirestoreError(error, OperationType.CREATE, `bookings/${bookingRef}`);
      }
    } finally {
      setIsBookingProcessing(false);
    }
  };

  const handleConfirmPayment = async (booking: BookingRecord) => {
    if (!currentUser) return;
    setIsBookingProcessing(true);
    const txnId = sanitizeId(`TXN-${Date.now().toString(36).toUpperCase()}`, 64);
    const bookingDocRef = doc(db, 'bookings', booking.bookingRef);

    try {
      const batch = writeBatch(db);
      batch.update(bookingDocRef, {
        status: 'confirmed',
        paymentStatus: 'paid',
        paymentTxnId: txnId,
        updatedAt: serverTimestamp(),
      });
      await batch.commit();

      const updated: BookingRecord = {
        ...booking,
        status: 'confirmed',
        paymentStatus: 'paid',
        paymentTxnId: txnId,
      };
      setActiveTicketModal(updated);
      showToast('success', `Payment verified (${txnId}). Your QR E-Ticket is confirmed!`);
    } catch (error) {
      handleFirestoreError(error, OperationType.UPDATE, `bookings/${booking.bookingRef}`);
    } finally {
      setIsBookingProcessing(false);
    }
  };

  const handleCancelBooking = async (booking: BookingRecord) => {
    if (!currentUser) return;
    setIsBookingProcessing(true);
    const uid = sanitizeId(currentUser.uid);
    const showRef = doc(db, 'shows', booking.showId);
    const bookingDocRef = doc(db, 'bookings', booking.bookingRef);

    try {
      await runTransaction(db, async (transaction) => {
        const showSnap = await transaction.get(showRef);
        if (showSnap.exists()) {
          const currentBooked: string[] = Array.isArray(showSnap.data().bookedSeats)
            ? showSnap.data().bookedSeats
            : [];
          const remainingSeats = currentBooked.filter((s) => !booking.seats.includes(s));
          transaction.update(showRef, {
            bookedSeats: remainingSeats,
            lastBookedBy: uid,
            updatedAt: serverTimestamp(),
          });
        }
        transaction.update(bookingDocRef, {
          status: 'cancelled',
          paymentStatus: 'refunded',
          updatedAt: serverTimestamp(),
        });
      });

      setActiveTicketModal((prev) =>
        prev && prev.bookingRef === booking.bookingRef
          ? { ...prev, status: 'cancelled', paymentStatus: 'refunded' }
          : prev
      );
      showToast('success', `Booking ${booking.bookingRef} cancelled and seats released.`);
    } catch (error) {
      handleFirestoreError(error, OperationType.UPDATE, `bookings/${booking.bookingRef}`);
    } finally {
      setIsBookingProcessing(false);
    }
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentUser) return;
    setProfileSaving(true);
    const uid = sanitizeId(currentUser.uid);
    const userDocRef = doc(db, 'users', uid);
    const privateDocRef = doc(db, 'users', uid, 'private', 'info');

    try {
      const userSnap = await getDoc(userDocRef);
      const batch = writeBatch(db);
      const safeName = (profileDisplayName.trim() || 'Cinema Guest').slice(
        0,
        VALIDATION_RULES.DISPLAY_NAME_MAX
      );
      const safeCity = (profileCity.trim() || 'Mumbai').slice(0, VALIDATION_RULES.CITY_MAX);
      const safePhone = profilePhone.trim().slice(0, VALIDATION_RULES.PHONE_MAX);
      const safeEmail = (currentUser.email || 'guest@example.com').slice(0, VALIDATION_RULES.EMAIL_MAX);

      if (!userSnap.exists()) {
        batch.set(userDocRef, {
          uid,
          displayName: safeName,
          preferredCity: safeCity,
          createdAt: serverTimestamp(),
          updatedAt: serverTimestamp(),
        });
        batch.set(privateDocRef, {
          uid,
          email: safeEmail,
          phone: safePhone,
          createdAt: serverTimestamp(),
          updatedAt: serverTimestamp(),
        });
      } else {
        batch.update(userDocRef, {
          displayName: safeName,
          preferredCity: safeCity,
          updatedAt: serverTimestamp(),
        });
        batch.update(privateDocRef, {
          email: safeEmail,
          phone: safePhone,
          updatedAt: serverTimestamp(),
        });
      }

      await batch.commit();
      showToast('success', 'Profile preferences updated.');
    } catch (error) {
      handleFirestoreError(error, OperationType.UPDATE, `users/${uid}`);
    } finally {
      setProfileSaving(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#090d16] text-slate-100">
      {/* Strict 3-Zone Top Bar Contract */}
      <header className="no-print sticky top-0 z-40 flex items-center justify-between gap-8 border-b border-slate-800/80 bg-[#090d16]/95 px-6 py-4 backdrop-blur-md">
        <button
          type="button"
          onClick={() => {
            setSelectedMovie(null);
            setSelectedShow(null);
            setActiveTab('movies');
          }}
          className="text-xl font-bold tracking-tight text-white whitespace-nowrap shrink-0 font-display"
        >
          MyBook<span className="text-rose-500">Show</span>
        </button>

        <nav className="hidden md:flex items-center gap-7 text-sm font-medium text-slate-300">
          <button
            type="button"
            onClick={() => {
              setSelectedMovie(null);
              setSelectedShow(null);
              setActiveTab('movies');
            }}
            className={`hover:text-white transition-colors whitespace-nowrap shrink-0 ${
              activeTab === 'movies'
                ? 'text-white underline decoration-rose-500 decoration-2 underline-offset-8'
                : ''
            }`}
          >
            Movies
          </button>
          <button
            type="button"
            onClick={() => {
              setSelectedMovie(null);
              setSelectedShow(null);
              setActiveTab('theatres');
            }}
            className={`hover:text-white transition-colors whitespace-nowrap shrink-0 ${
              activeTab === 'theatres'
                ? 'text-white underline decoration-rose-500 decoration-2 underline-offset-8'
                : ''
            }`}
          >
            Theatres
          </button>
          <button
            type="button"
            onClick={() => {
              setSelectedMovie(null);
              setSelectedShow(null);
              setActiveTab('bookings');
            }}
            className={`hover:text-white transition-colors whitespace-nowrap shrink-0 ${
              activeTab === 'bookings'
                ? 'text-white underline decoration-rose-500 decoration-2 underline-offset-8'
                : ''
            }`}
          >
            My Bookings
          </button>
          <button
            type="button"
            onClick={() => {
              setSelectedMovie(null);
              setSelectedShow(null);
              setActiveTab('profile');
            }}
            className={`hover:text-white transition-colors whitespace-nowrap shrink-0 ${
              activeTab === 'profile'
                ? 'text-white underline decoration-rose-500 decoration-2 underline-offset-8'
                : ''
            }`}
          >
            Profile
          </button>
          <button
            type="button"
            onClick={() => {
              setSelectedMovie(null);
              setSelectedShow(null);
              setActiveTab('architecture');
            }}
            className={`hover:text-white transition-colors whitespace-nowrap shrink-0 ${
              activeTab === 'architecture'
                ? 'text-white underline decoration-rose-500 decoration-2 underline-offset-8'
                : ''
            }`}
          >
            Django Stack
          </button>
        </nav>

        <div className="flex items-center gap-3 shrink-0">
          {currentUser ? (
            <button
              type="button"
              onClick={() => signOutUser()}
              className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800 transition-colors whitespace-nowrap shrink-0"
            >
              Sign Out
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSignIn}
              className="rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-500 transition-colors whitespace-nowrap shrink-0"
            >
              Sign In
            </button>
          )}
        </div>
      </header>

      {/* Mobile Navigation Strip */}
      <div className="no-print flex md:hidden items-center justify-around border-b border-slate-800 bg-[#111827] px-3 py-2 text-xs font-medium text-slate-300">
        {(['movies', 'theatres', 'bookings', 'profile', 'architecture'] as ActiveTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => {
              setSelectedMovie(null);
              setSelectedShow(null);
              setActiveTab(tab);
            }}
            className={`px-2 py-1 capitalize whitespace-nowrap shrink-0 ${
              activeTab === tab ? 'text-rose-400 font-semibold' : 'text-slate-400'
            }`}
          >
            {tab === 'architecture' ? 'Django' : tab}
          </button>
        ))}
      </div>

      {/* Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-xl border border-slate-700 bg-[#111827] px-4 py-3 text-xs font-medium text-white shadow-2xl">
          {toast.type === 'success' ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 text-rose-400 shrink-0" />
          )}
          <span>{toast.message}</span>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-grow">
        {/* VIEW 1: MOVIES CATALOG & INTERACTIVE BOOKING FLOW */}
        {activeTab === 'movies' && !selectedMovie && (
          <>
            {/* Storefront Split Hero */}
            <section className="border-b border-slate-800/80 bg-[#0c1220]">
              <div className="mx-auto max-w-[1200px] px-6 py-10 lg:py-14">
                <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-stretch">
                  <div className="flex flex-col justify-between lg:col-span-6">
                    <div>
                      <div className="flex items-center gap-2 text-xs text-slate-400">
                        <span>IMAX Dual 4K Laser</span>
                        <span aria-hidden="true">·</span>
                        <span>Dolby Atmos Auditoriums</span>
                        <span aria-hidden="true">·</span>
                        <span>Mumbai, Delhi &amp; Bengaluru</span>
                      </div>
                      <h1
                        className="mt-3 font-bold tracking-tight text-white font-display"
                        style={{ fontSize: 'clamp(2.25rem, 3.8vw, 3.4rem)', lineHeight: 1.1 }}
                      >
                        Premiere Cinema Seat Reservations, Engineered for Zero Contention.
                      </h1>
                      <p className="mt-4 max-w-xl text-base text-slate-300 leading-relaxed">
                        Select your exact auditorium row and recliner seat in real time. Powered by transactional row-level locking, instant QR e-ticket generation, and verified showtime schedules.
                      </p>
                    </div>

                    <div className="mt-8 flex flex-wrap items-center gap-4">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedMovie(MOVIES_CATALOG[0]);
                          setSelectedDate(AVAILABLE_DATES[0].date);
                        }}
                        className="rounded-lg bg-rose-600 px-6 py-3 text-sm font-semibold text-white hover:bg-rose-500 transition-colors whitespace-nowrap shrink-0"
                      >
                        Book Chronos Horizon (IMAX)
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTab('theatres')}
                        className="rounded-lg border border-slate-700 bg-slate-900/80 px-5 py-3 text-sm font-medium text-slate-200 hover:bg-slate-800 transition-colors whitespace-nowrap shrink-0"
                      >
                        Explore Partner Theatres
                      </button>
                    </div>
                  </div>

                  <div className="lg:col-span-6">
                    <div className="relative h-full min-h-[280px] overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
                      {!brokenImages['hero'] ? (
                        <img
                          src={HERO_BANNER_IMAGE}
                          alt="MyBookShow Grand IMAX Laser Auditorium"
                          referrerPolicy="no-referrer"
                          onError={() => setBrokenImages((p) => ({ ...p, hero: true }))}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-slate-900 to-rose-950 p-8 text-center">
                          <Film className="h-10 w-10 text-rose-500" />
                          <span className="mt-2 font-display text-lg font-semibold text-white">
                            MyBookShow Grand IMAX Auditorium
                          </span>
                        </div>
                      )}
                      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent" />
                      <div className="absolute bottom-4 left-5 right-5 flex items-end justify-between gap-4">
                        <div>
                          <div className="text-xs text-slate-300">
                            Featured Premiere <span aria-hidden="true">·</span> Sci-Fi <span aria-hidden="true">·</span> UA
                          </div>
                          <div className="text-lg font-bold text-white font-display">
                            Chronos Horizon — Now Screening in IMAX Laser
                          </div>
                        </div>
                        <span className="font-mono text-xs text-slate-300 shrink-0">154 mins</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Full-Width 4-Column Quick Filter & Search Bar Below Hero Split */}
                <div className="mt-8 grid grid-cols-1 gap-4 rounded-xl border border-slate-800 bg-[#111827] p-4 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="relative flex items-center">
                    <Search className="pointer-events-none absolute left-3.5 h-4 w-4 text-slate-400" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search title, cast, director..."
                      aria-label="Search movies by title, cast, or director"
                      className="w-full rounded-lg border border-slate-700 bg-[#090d16] py-2 pl-10 pr-3 text-xs text-white placeholder-slate-500 focus:border-rose-500 focus:outline-none"
                    />
                  </div>

                  <div className="flex items-center gap-1 rounded-lg bg-[#090d16] p-1 border border-slate-800">
                    {(
                      [
                        { id: 'all', label: 'All Releases' },
                        { id: 'now_showing', label: 'Now Showing' },
                        { id: 'coming_soon', label: 'Coming Soon' },
                      ] as const
                    ).map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setSelectedStatus(item.id)}
                        className={`flex-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                          selectedStatus === item.id
                            ? 'bg-rose-600 text-white'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-2">
                    <select
                      aria-label="Filter by Genre"
                      value={selectedGenre}
                      onChange={(e) => setSelectedGenre(e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-[#090d16] px-3 py-2 text-xs text-slate-200 focus:border-rose-500 focus:outline-none"
                    >
                      <option value="all">All Genres</option>
                      <option value="Sci-Fi">Sci-Fi</option>
                      <option value="Mystery">Mystery</option>
                      <option value="Thriller">Thriller</option>
                      <option value="Drama">Drama</option>
                    </select>

                    <select
                      aria-label="Filter by Language"
                      value={selectedLanguage}
                      onChange={(e) => setSelectedLanguage(e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-[#090d16] px-3 py-2 text-xs text-slate-200 focus:border-rose-500 focus:outline-none"
                    >
                      <option value="all">All Languages</option>
                      <option value="English">English</option>
                      <option value="Hindi">Hindi</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-2">
                    <SlidersHorizontal className="h-4 w-4 text-slate-400 shrink-0" />
                    <select
                      aria-label="Sort movies"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value as 'release' | 'title' | 'duration')}
                      className="w-full rounded-lg border border-slate-700 bg-[#090d16] px-3 py-2 text-xs text-slate-200 focus:border-rose-500 focus:outline-none"
                    >
                      <option value="release">Sort: Newest Releases</option>
                      <option value="title">Sort: Title (A–Z)</option>
                      <option value="duration">Sort: Shortest Duration</option>
                    </select>
                  </div>
                </div>
              </div>
            </section>

            {/* Movie Poster Grid */}
            <section className="mx-auto max-w-[1200px] px-6 py-12">
              <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-white font-display">
                    Curated Theatrical Lineup
                  </h2>
                  <p className="mt-1 text-sm text-slate-400">
                    Select a motion picture to view auditorium showtimes and interactive seat availability
                  </p>
                </div>
                <div className="text-xs text-slate-400 font-mono tabular-nums">
                  Showing {filteredMovies.length} of {MOVIES_CATALOG.length} titles
                </div>
              </div>

              {filteredMovies.length === 0 ? (
                <div className="rounded-xl border border-slate-800 bg-[#111827] p-12 text-center">
                  <p className="text-base font-medium text-white">No movies matched your filter criteria</p>
                  <p className="mt-1 text-xs text-slate-400">
                    Try clearing your search query or switching back to All Genres and All Languages.
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setSearchQuery('');
                      setSelectedGenre('all');
                      setSelectedLanguage('all');
                      setSelectedStatus('all');
                    }}
                    className="mt-4 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-500 transition-colors"
                  >
                    Reset Filters
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-7 sm:grid-cols-2 lg:grid-cols-4">
                  {filteredMovies.map((movie) => (
                    <article
                      key={movie.id}
                      className="group flex flex-col overflow-hidden rounded-xl border border-slate-800/90 bg-[#111827] transition-transform duration-150 hover:-translate-y-0.5"
                    >
                      <div className="relative aspect-[3/4] w-full overflow-hidden bg-[#090d16]">
                        {!brokenImages[movie.id] ? (
                          <img
                            src={movie.poster}
                            alt={`${movie.title} theatrical poster`}
                            referrerPolicy="no-referrer"
                            onError={() => setBrokenImages((p) => ({ ...p, [movie.id]: true }))}
                            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                          />
                        ) : (
                          <div className="flex h-full w-full flex-col items-center justify-center bg-slate-900 p-6 text-center">
                            <Film className="h-8 w-8 text-rose-500" />
                            <span className="mt-2 font-display text-sm font-semibold text-white">
                              {movie.title}
                            </span>
                          </div>
                        )}
                        <div className="absolute inset-0 bg-gradient-to-t from-[#111827] via-transparent to-transparent opacity-90" />
                        <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between text-xs text-slate-200 font-mono tabular-nums">
                          <span>{movie.rating}</span>
                          <span>{movie.durationMinutes} mins</span>
                        </div>
                      </div>

                      <div className="flex flex-1 flex-col justify-between p-5">
                        <div>
                          {/* Clean Unboxed Metadata with Typographic Separators (Zero-Pill Rule) */}
                          <div className="flex items-center gap-1.5 text-xs text-slate-400">
                            <span>{movie.genre}</span>
                            <span aria-hidden="true">·</span>
                            <span>{movie.language}</span>
                            <span aria-hidden="true">·</span>
                            <span>Certificate {movie.certificate}</span>
                          </div>

                          <h3 className="mt-1.5 text-lg font-bold text-white font-display">
                            {movie.title}
                          </h3>

                          <p className="mt-2 text-xs text-slate-400 line-clamp-3 leading-relaxed">
                            {movie.description}
                          </p>
                        </div>

                        <div className="mt-5 pt-3 border-t border-slate-800/80">
                          <div className="text-[11px] text-slate-400 truncate mb-3">
                            Dir. {movie.director}
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedMovie(movie);
                              const firstShow = SHOWTIMES_CATALOG.find((s) => s.movieId === movie.id);
                              if (firstShow) {
                                setSelectedDate(firstShow.showDate);
                              }
                            }}
                            className="w-full rounded-lg bg-rose-600 py-2.5 px-4 text-xs font-semibold text-white hover:bg-rose-500 transition-colors whitespace-nowrap shrink-0"
                          >
                            {movie.status === 'now_showing' ? 'Select Showtime & Seats' : 'Advance Booking Open'}
                          </button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </>
        )}

        {/* VIEW 2: MOVIE DETAILS, SHOWTIME SELECTION & AUDITORIUM SEAT MAP */}
        {activeTab === 'movies' && selectedMovie && (
          <section className="mx-auto max-w-[1200px] px-6 py-10">
            <button
              type="button"
              onClick={() => {
                setSelectedMovie(null);
                setSelectedShow(null);
              }}
              className="inline-flex items-center gap-2 text-xs font-medium text-slate-400 hover:text-white transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              <span>Back to All Movies</span>
            </button>

            {/* Movie Header */}
            <div className="mt-6 grid grid-cols-1 gap-8 rounded-xl border border-slate-800 bg-[#111827] p-6 lg:grid-cols-12">
              <div className="lg:col-span-3">
                <div className="aspect-[3/4] w-full max-w-[240px] overflow-hidden rounded-lg border border-slate-800 bg-[#090d16]">
                  <img
                    src={selectedMovie.poster}
                    alt={selectedMovie.title}
                    referrerPolicy="no-referrer"
                    className="h-full w-full object-cover"
                  />
                </div>
              </div>

              <div className="lg:col-span-9 flex flex-col justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                    <span>{selectedMovie.genre}</span>
                    <span aria-hidden="true">·</span>
                    <span>{selectedMovie.language}</span>
                    <span aria-hidden="true">·</span>
                    <span>Certificate {selectedMovie.certificate}</span>
                    <span aria-hidden="true">·</span>
                    <span className="font-mono">{selectedMovie.durationMinutes} mins</span>
                    <span aria-hidden="true">·</span>
                    <span>Release {selectedMovie.releaseDate}</span>
                  </div>

                  <h1 className="mt-2 text-3xl font-bold text-white font-display">
                    {selectedMovie.title}
                  </h1>

                  <p className="mt-3 max-w-3xl text-sm text-slate-300 leading-relaxed">
                    {selectedMovie.description}
                  </p>

                  <div className="mt-4 space-y-1 text-xs text-slate-400">
                    <div>
                      <span className="text-slate-200 font-medium">Director:</span> {selectedMovie.director}
                    </div>
                    <div>
                      <span className="text-slate-200 font-medium">Principal Cast:</span> {selectedMovie.cast}
                    </div>
                  </div>
                </div>

                {/* Date & City Filter Controls */}
                <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-slate-800 pt-5">
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-rose-500 shrink-0" />
                    <div className="flex items-center gap-1 rounded-lg bg-[#090d16] p-1 border border-slate-800">
                      {AVAILABLE_DATES.map((d) => (
                        <button
                          key={d.date}
                          type="button"
                          onClick={() => {
                            setSelectedDate(d.date);
                            setSelectedShow(null);
                          }}
                          className={`rounded-md px-3 py-1.5 text-xs font-medium font-mono transition-colors whitespace-nowrap shrink-0 ${
                            selectedDate === d.date
                              ? 'bg-rose-600 text-white'
                              : 'text-slate-400 hover:text-white'
                          }`}
                        >
                          {d.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-rose-500 shrink-0" />
                    <div className="flex items-center gap-1 rounded-lg bg-[#090d16] p-1 border border-slate-800">
                      {['All Cities', 'Mumbai', 'Delhi', 'Bengaluru'].map((city) => (
                        <button
                          key={city}
                          type="button"
                          onClick={() => {
                            setSelectedCity(city);
                            setSelectedShow(null);
                          }}
                          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                            selectedCity === city
                              ? 'bg-slate-800 text-white'
                              : 'text-slate-400 hover:text-white'
                          }`}
                        >
                          {city}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Showtimes List */}
            <div className="mt-8">
              <h2 className="text-xl font-bold text-white font-display">
                1. Select Theatre &amp; Showtime
              </h2>
              {movieShowtimes.length === 0 ? (
                <div className="mt-4 rounded-xl border border-slate-800 bg-[#111827] p-6 text-sm text-slate-400">
                  No showtimes scheduled on {selectedDate} for {selectedCity}. Try selecting another date tab above.
                </div>
              ) : (
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                  {movieShowtimes.map((show) => {
                    const isSelected = selectedShow?.id === show.id;
                    return (
                      <div
                        key={show.id}
                        className={`rounded-xl border p-5 transition-colors ${
                          isSelected
                            ? 'border-rose-500 bg-rose-950/15'
                            : 'border-slate-800 bg-[#111827] hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <div className="text-xs text-slate-400">
                              {show.city} <span aria-hidden="true">·</span> {show.screenName} <span aria-hidden="true">·</span> {show.soundSystem}
                            </div>
                            <h3 className="mt-1 text-base font-bold text-white">{show.theatreName}</h3>
                            <div className="mt-1 text-xs text-slate-400 font-mono tabular-nums">
                              Standard ₹{show.priceStandard} · Executive ₹{show.priceExecutive} · Royal ₹{show.priceRoyal}
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => setSelectedShow(show)}
                            className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-mono font-semibold transition-colors whitespace-nowrap shrink-0 ${
                              isSelected
                                ? 'bg-rose-600 text-white'
                                : 'border border-slate-700 bg-[#090d16] text-slate-200 hover:border-rose-500'
                            }`}
                          >
                            <Clock className="h-3.5 w-3.5" />
                            <span>{show.startTime} IST</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Interactive Auditorium Seat Map & Contiguous Checkout Module */}
            {selectedShow && (
              <div className="mt-10 grid grid-cols-1 gap-8 lg:grid-cols-12">
                {/* Auditorium Seat Map */}
                <div className="lg:col-span-8 rounded-xl border border-slate-800 bg-[#111827] p-6">
                  <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
                    <div>
                      <h3 className="text-lg font-bold text-white font-display">
                        2. Select Auditorium Seats — {selectedShow.screenName}
                      </h3>
                      <p className="text-xs text-slate-400">
                        Real-time seat occupancy synced via transactional lock
                      </p>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-slate-300">
                      <span className="flex items-center gap-1.5">
                        <span className="inline-block h-3.5 w-3.5 rounded border border-slate-600 bg-[#090d16]" />
                        <span>Available</span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="inline-block h-3.5 w-3.5 rounded bg-rose-600" />
                        <span>Selected</span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="inline-block h-3.5 w-3.5 rounded bg-slate-800 text-slate-600" />
                        <span>Booked</span>
                      </span>
                    </div>
                  </div>

                  {/* Screen Arc Indicator */}
                  <div className="my-8 text-center">
                    <div className="mx-auto h-3 max-w-md rounded-t-full border-t-2 border-rose-500/80 bg-gradient-to-b from-rose-500/20 to-transparent" />
                    <span className="mt-2 block text-[11px] tracking-wider text-slate-400">
                      Auditorium Projection Screen — All Eyes This Way
                    </span>
                  </div>

                  {/* Seat Grid */}
                  <div className="space-y-3 overflow-x-auto pb-2">
                    {AUDITORIUM_ROWS.map((rowMeta) => {
                      const rowPrice = getSeatPrice(selectedShow, rowMeta.tier);
                      return (
                        <div
                          key={rowMeta.row}
                          className="flex items-center justify-between gap-4 min-w-[460px]"
                        >
                          <div className="w-28 text-xs text-slate-400 font-mono tabular-nums">
                            <span className="font-bold text-slate-200">Row {rowMeta.row}</span> · ₹{rowPrice}
                          </div>

                          <div className="flex items-center gap-2">
                            {Array.from({ length: 8 }, (_, idx) => {
                              const num = idx + 1;
                              const code = `${rowMeta.row}${num}`;
                              const isBooked = liveBookedSeats.includes(code);
                              const isSelected = selectedSeats.includes(code);
                              return (
                                <React.Fragment key={code}>
                                  {num === 5 && <div className="w-4" aria-hidden="true" />}
                                  <button
                                    type="button"
                                    disabled={isBooked}
                                    onClick={() => handleToggleSeat(code)}
                                    aria-label={`Seat ${code} (${rowMeta.tierLabel}, ₹${rowPrice}) - ${
                                      isBooked ? 'Booked' : isSelected ? 'Selected' : 'Available'
                                    }`}
                                    className={`h-9 w-10 rounded-md font-mono text-xs font-medium transition-colors ${
                                      isBooked
                                        ? 'cursor-not-allowed border border-slate-800 bg-slate-900 text-slate-600'
                                        : isSelected
                                          ? 'bg-rose-600 text-white font-semibold shadow-sm'
                                          : 'border border-slate-700 bg-[#090d16] text-slate-200 hover:border-rose-500 hover:text-white'
                                    }`}
                                  >
                                    {code}
                                  </button>
                                </React.Fragment>
                              );
                            })}
                          </div>

                          <div className="w-24 text-right text-[11px] text-slate-400">
                            {rowMeta.tierLabel}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Contiguous Purchase Summary Module */}
                <div className="lg:col-span-4 rounded-xl border border-slate-800 bg-[#111827] p-6 flex flex-col justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-white font-display">
                      3. Reservation Summary
                    </h3>
                    <div className="mt-3 space-y-1 text-xs text-slate-400">
                      <div className="font-semibold text-white text-sm">{selectedMovie.title}</div>
                      <div>{selectedShow.theatreName}</div>
                      <div className="font-mono text-slate-300">
                        {selectedShow.showDate} · {selectedShow.startTime} IST · {selectedShow.screenName}
                      </div>
                    </div>

                    <div className="mt-6 border-t border-b border-slate-800 py-4 space-y-2.5 text-sm font-mono tabular-nums">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Selected Seats</span>
                        <span className="font-semibold text-white">
                          {selectedSeats.length > 0 ? selectedSeats.join(', ') : 'None'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Tickets Subtotal</span>
                        <span className="text-slate-200">₹{pricingSummary.subtotal.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-xs text-slate-400">
                        <span>Convenience Fee (8%)</span>
                        <span>₹{pricingSummary.convenienceFee.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between pt-2 border-t border-slate-800 text-base font-bold text-white">
                        <span>Total Payable</span>
                        <span>₹{pricingSummary.total.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-6 space-y-3">
                    <button
                      type="button"
                      disabled={selectedSeats.length === 0 || isBookingProcessing}
                      onClick={handleCreateBooking}
                      className="w-full rounded-lg bg-rose-600 py-3 px-4 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-40 transition-colors whitespace-nowrap shrink-0"
                    >
                      {isBookingProcessing
                        ? 'Locking Seats in Transaction...'
                        : selectedSeats.length === 0
                          ? 'Select Seats on Map to Continue'
                          : `Lock ${selectedSeats.length} ${
                              selectedSeats.length === 1 ? 'Seat' : 'Seats'
                            } & Proceed (₹${pricingSummary.total.toFixed(2)})`}
                    </button>
                    <p className="text-[11px] text-slate-400 text-center">
                      Protected against concurrent double-booking. Cancellations allowed up to 2 hours before showtime.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        {/* VIEW 3: PARTNER THEATRES */}
        {activeTab === 'theatres' && (
          <section className="mx-auto max-w-[1200px] px-6 py-12">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-slate-800 pb-6">
              <div>
                <h1 className="text-3xl font-bold text-white font-display">
                  Partner Theatres &amp; Auditoriums
                </h1>
                <p className="mt-1 text-sm text-slate-400">
                  Flagship IMAX Laser and Dolby Atmos locations across India
                </p>
              </div>
              <div className="flex items-center gap-1 rounded-lg bg-[#111827] p-1 border border-slate-800">
                {['All Cities', 'Mumbai', 'Delhi', 'Bengaluru'].map((city) => (
                  <button
                    key={city}
                    type="button"
                    onClick={() => setSelectedCity(city)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                      selectedCity === city ? 'bg-rose-600 text-white' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {city}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
              {THEATRES_CATALOG.filter(
                (t) => selectedCity === 'All Cities' || t.city === selectedCity
              ).map((theatre) => (
                <div
                  key={theatre.id}
                  className="flex flex-col justify-between rounded-xl border border-slate-800 bg-[#111827] p-6"
                >
                  <div>
                    <div className="text-xs text-rose-400 font-medium">{theatre.city}</div>
                    <h2 className="mt-1 text-lg font-bold text-white font-display">{theatre.name}</h2>
                    <p className="mt-1.5 text-xs text-slate-400">{theatre.address}</p>
                    <div className="mt-3 text-xs text-slate-300">{theatre.amenities}</div>

                    <div className="mt-5 border-t border-slate-800 pt-4 space-y-2">
                      <div className="text-xs font-semibold text-slate-300">Configured Screens</div>
                      {theatre.screens.map((scr) => (
                        <div
                          key={scr.id}
                          className="flex items-center justify-between text-xs text-slate-400 font-mono"
                        >
                          <span>{scr.name}</span>
                          <span>
                            {scr.soundSystem} · {scr.totalSeats} Seats
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCity(theatre.city);
                      setActiveTab('movies');
                    }}
                    className="mt-6 w-full rounded-lg border border-slate-700 bg-[#090d16] py-2.5 text-xs font-semibold text-white hover:border-rose-500 transition-colors"
                  >
                    Browse Showtimes in {theatre.city}
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* VIEW 4: MY BOOKINGS HISTORY */}
        {activeTab === 'bookings' && (
          <section className="mx-auto max-w-[1200px] px-6 py-12">
            <div className="border-b border-slate-800 pb-6">
              <h1 className="text-3xl font-bold text-white font-display">My Booking History</h1>
              <p className="mt-1 text-sm text-slate-400">
                View your confirmed QR e-tickets, complete pending sandbox payments, or cancel reservations up to 2 hours before showtime
              </p>
            </div>

            {!currentUser ? (
              <div className="mt-8 rounded-xl border border-slate-800 bg-[#111827] p-10 text-center">
                <Ticket className="mx-auto h-8 w-8 text-rose-500" />
                <h2 className="mt-3 text-lg font-bold text-white font-display">
                  Sign In to View Your Bookings
                </h2>
                <p className="mt-1 text-xs text-slate-400">
                  Your reservations and printable QR e-tickets are linked to your verified account.
                </p>
                <button
                  type="button"
                  onClick={handleSignIn}
                  className="mt-5 rounded-lg bg-rose-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-rose-500 transition-colors"
                >
                  Sign In with Google
                </button>
              </div>
            ) : userBookings.length === 0 ? (
              <div className="mt-8 rounded-xl border border-slate-800 bg-[#111827] p-10 text-center">
                <Ticket className="mx-auto h-8 w-8 text-slate-500" />
                <h2 className="mt-3 text-lg font-bold text-white font-display">No Bookings Yet</h2>
                <p className="mt-1 text-xs text-slate-400">
                  Select a movie and lock your auditorium seats to generate your first e-ticket.
                </p>
                <button
                  type="button"
                  onClick={() => setActiveTab('movies')}
                  className="mt-5 rounded-lg bg-rose-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-rose-500 transition-colors"
                >
                  Explore Movies
                </button>
              </div>
            ) : (
              <div className="mt-8 space-y-4">
                {userBookings.map((booking) => (
                  <div
                    key={booking.bookingRef}
                    className="flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-xl border border-slate-800 bg-[#111827] p-5"
                  >
                    <div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                        <span className="font-mono font-semibold text-white">{booking.bookingRef}</span>
                        <span aria-hidden="true">·</span>
                        <span
                          className={
                            booking.status === 'confirmed'
                              ? 'text-emerald-400 font-medium'
                              : booking.status === 'pending_payment'
                                ? 'text-amber-400 font-medium'
                                : 'text-rose-400 font-medium'
                          }
                        >
                          {booking.status === 'confirmed'
                            ? 'Confirmed'
                            : booking.status === 'pending_payment'
                              ? 'Pending Payment Verification'
                              : 'Cancelled & Refunded'}
                        </span>
                        <span aria-hidden="true">·</span>
                        <span className="font-mono">
                          {booking.showDate} {booking.startTime} IST
                        </span>
                      </div>

                      <h2 className="mt-1 text-lg font-bold text-white font-display">
                        {booking.movieTitle}
                      </h2>
                      <div className="mt-0.5 text-xs text-slate-400">
                        {booking.theatreName} <span aria-hidden="true">·</span> {booking.screenName}{' '}
                        <span aria-hidden="true">·</span> Seats:{' '}
                        <span className="font-mono text-slate-200">{booking.seats.join(', ')}</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <div className="text-right font-mono mr-2">
                        <div className="text-sm font-bold text-white">
                          ₹{booking.totalAmount.toFixed(2)}
                        </div>
                        <div className="text-[11px] text-slate-400">{booking.paymentTxnId}</div>
                      </div>

                      <button
                        type="button"
                        onClick={() => setActiveTicketModal(booking)}
                        className="rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-500 transition-colors whitespace-nowrap shrink-0"
                      >
                        {booking.status === 'pending_payment' ? 'Verify Payment / Ticket' : 'View QR Ticket'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* VIEW 5: USER PROFILE & PREFERENCES */}
        {activeTab === 'profile' && (
          <section className="mx-auto max-w-[760px] px-6 py-12">
            <div className="border-b border-slate-800 pb-6">
              <h1 className="text-3xl font-bold text-white font-display">Account &amp; Profile</h1>
              <p className="mt-1 text-sm text-slate-400">
                Manage your display name, preferred cinema city, and isolated contact information
              </p>
            </div>

            {!currentUser ? (
              <div className="mt-8 rounded-xl border border-slate-800 bg-[#111827] p-10 text-center">
                <UserIcon className="mx-auto h-8 w-8 text-rose-500" />
                <h2 className="mt-3 text-lg font-bold text-white font-display">
                  Sign In to Manage Your Profile
                </h2>
                <button
                  type="button"
                  onClick={handleSignIn}
                  className="mt-5 rounded-lg bg-rose-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-rose-500 transition-colors"
                >
                  Sign In with Google
                </button>
              </div>
            ) : (
              <form
                onSubmit={handleSaveProfile}
                className="mt-8 space-y-5 rounded-xl border border-slate-800 bg-[#111827] p-6"
              >
                <div>
                  <label className="block text-xs font-medium text-slate-300">
                    Verified Email Address (PII Split-Collection Protected)
                  </label>
                  <input
                    type="email"
                    disabled
                    value={currentUser.email || ''}
                    className="mt-1.5 w-full rounded-lg border border-slate-800 bg-[#090d16] px-3.5 py-2 text-xs text-slate-400 font-mono"
                  />
                </div>

                <div>
                  <label htmlFor="profile-name" className="block text-xs font-medium text-slate-300">
                    Full Name on E-Tickets
                  </label>
                  <input
                    id="profile-name"
                    type="text"
                    required
                    maxLength={VALIDATION_RULES.DISPLAY_NAME_MAX}
                    value={profileDisplayName}
                    onChange={(e) => setProfileDisplayName(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-slate-700 bg-[#090d16] px-3.5 py-2 text-xs text-white focus:border-rose-500 focus:outline-none"
                  />
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="profile-city" className="block text-xs font-medium text-slate-300">
                      Preferred Cinema City
                    </label>
                    <select
                      id="profile-city"
                      value={profileCity}
                      onChange={(e) => setProfileCity(e.target.value)}
                      className="mt-1.5 w-full rounded-lg border border-slate-700 bg-[#090d16] px-3.5 py-2 text-xs text-white focus:border-rose-500 focus:outline-none"
                    >
                      <option value="Mumbai">Mumbai</option>
                      <option value="Delhi">Delhi</option>
                      <option value="Bengaluru">Bengaluru</option>
                    </select>
                  </div>

                  <div>
                    <label htmlFor="profile-phone" className="block text-xs font-medium text-slate-300">
                      Mobile Number (For SMS Alerts)
                    </label>
                    <input
                      id="profile-phone"
                      type="tel"
                      maxLength={VALIDATION_RULES.PHONE_MAX}
                      placeholder="+91 98765 43210"
                      value={profilePhone}
                      onChange={(e) => setProfilePhone(e.target.value)}
                      className="mt-1.5 w-full rounded-lg border border-slate-700 bg-[#090d16] px-3.5 py-2 text-xs text-white focus:border-rose-500 focus:outline-none font-mono"
                    />
                  </div>
                </div>

                <div className="pt-2 flex items-center justify-end">
                  <button
                    type="submit"
                    disabled={profileSaving}
                    className="rounded-lg bg-rose-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50 transition-colors"
                  >
                    {profileSaving ? 'Saving Preferences...' : 'Save Profile Preferences'}
                  </button>
                </div>
              </form>
            )}
          </section>
        )}

        {/* VIEW 6: DJANGO + SUPABASE + RENDER + VERCEL ARCHITECTURE */}
        {activeTab === 'architecture' && <DjangoBlueprintPanel />}
      </main>

      {/* Quiet Editorial Footer */}
      <footer className="no-print border-t border-slate-800/80 bg-[#090d16] py-8 px-6 text-xs text-slate-400">
        <div className="mx-auto max-w-[1200px] flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            &copy; {new Date().getFullYear()} MyBookShow. Built with Django 5.1, Supabase PostgreSQL (<span className="font-mono">iqxcgzrfjplernbidkfd</span>), Render &amp; Vercel.
          </div>
          <div className="flex items-center gap-6">
            <button
              type="button"
              onClick={() => setActiveTab('movies')}
              className="hover:text-white transition-colors"
            >
              Movies
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('theatres')}
              className="hover:text-white transition-colors"
            >
              Theatres
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('architecture')}
              className="hover:text-white transition-colors"
            >
              Django &amp; Supabase Docs
            </button>
          </div>
        </div>
      </footer>

      {/* Printable QR E-Ticket & Payment Verification Modal */}
      {activeTicketModal && (
        <TicketModal
          booking={activeTicketModal}
          onClose={() => setActiveTicketModal(null)}
          onConfirmPayment={handleConfirmPayment}
          onCancelBooking={handleCancelBooking}
          isProcessing={isBookingProcessing}
        />
      )}
    </div>
  );
}
