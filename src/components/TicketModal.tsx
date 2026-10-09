import React, { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { Printer, X, CheckCircle2, AlertTriangle, RotateCcw } from 'lucide-react';

export interface BookingRecord {
  bookingRef: string;
  userId: string;
  showId: string;
  movieId: string;
  movieTitle: string;
  theatreName: string;
  screenName: string;
  showDate: string;
  startTime: string;
  seats: string[];
  subtotalAmount: number;
  convenienceFee: number;
  totalAmount: number;
  status: 'pending_payment' | 'confirmed' | 'cancelled';
  paymentStatus: 'pending' | 'paid' | 'refunded';
  paymentTxnId: string;
}

interface TicketModalProps {
  booking: BookingRecord;
  onClose: () => void;
  onConfirmPayment: (booking: BookingRecord) => Promise<void>;
  onCancelBooking: (booking: BookingRecord) => Promise<void>;
  isProcessing: boolean;
}

export const TicketModal: React.FC<TicketModalProps> = ({
  booking,
  onClose,
  onConfirmPayment,
  onCancelBooking,
  isProcessing,
}) => {
  const [qrDataUrl, setQrDataUrl] = useState<string>('');

  useEffect(() => {
    const payload = [
      'MYBOOKSHOW_ETICKET',
      `REF:${booking.bookingRef}`,
      `MOVIE:${booking.movieTitle}`,
      `THEATRE:${booking.theatreName}`,
      `SCREEN:${booking.screenName}`,
      `SHOW:${booking.showDate} ${booking.startTime}`,
      `SEATS:${booking.seats.join(',')}`,
      `STATUS:${booking.status.toUpperCase()}`,
    ].join('|');

    QRCode.toDataURL(payload, {
      width: 200,
      margin: 2,
      color: {
        dark: '#090d16',
        light: '#ffffff',
      },
    })
      .then((url) => setQrDataUrl(url))
      .catch((err) => console.error('QR generation failed:', err));
  }, [booking]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ticket-modal-title"
    >
      <div className="relative w-full max-w-2xl rounded-xl border border-slate-800 bg-[#111827] p-6 md:p-8 text-slate-100 shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-5">
          <div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span>Booking Reference</span>
              <span aria-hidden="true">·</span>
              <span className="font-mono font-semibold text-white">{booking.bookingRef}</span>
              <span aria-hidden="true">·</span>
              <span
                className={
                  booking.status === 'confirmed'
                    ? 'font-medium text-emerald-400'
                    : booking.status === 'pending_payment'
                      ? 'font-medium text-amber-400'
                      : 'font-medium text-rose-400'
                }
              >
                {booking.status === 'confirmed'
                  ? 'Confirmed E-Ticket'
                  : booking.status === 'pending_payment'
                    ? 'Pending Payment Verification'
                    : 'Cancelled & Refunded'}
              </span>
            </div>
            <h2 id="ticket-modal-title" className="mt-1 text-2xl font-bold tracking-tight text-white font-display">
              {booking.movieTitle}
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              {booking.theatreName} <span aria-hidden="true">·</span> {booking.screenName}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="no-print rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            aria-label="Close ticket modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-3 md:items-center">
          <div className="md:col-span-2 space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-xs text-slate-400">Show Date &amp; Time</div>
                <div className="mt-0.5 font-mono font-semibold text-white">
                  {booking.showDate} <span aria-hidden="true">·</span> {booking.startTime} IST
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-400">Reserved Auditorium Seats</div>
                <div className="mt-0.5 font-mono font-semibold text-rose-400">
                  {booking.seats.join(', ')} ({booking.seats.length}{' '}
                  {booking.seats.length === 1 ? 'Seat' : 'Seats'})
                </div>
              </div>
            </div>

            <div className="border-t border-b border-slate-800 py-4 space-y-2 text-sm font-mono tabular-nums">
              <div className="flex justify-between text-slate-300">
                <span>Ticket Subtotal</span>
                <span>₹{booking.subtotalAmount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-400 text-xs">
                <span>Convenience &amp; Handling Fee (8%)</span>
                <span>₹{booking.convenienceFee.toFixed(2)}</span>
              </div>
              <div className="flex justify-between pt-2 border-t border-slate-800/80 text-base font-semibold text-white">
                <span>Total Amount</span>
                <span>₹{booking.totalAmount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-xs text-slate-400 pt-1">
                <span>Gateway Reference</span>
                <span>{booking.paymentTxnId}</span>
              </div>
            </div>

            {booking.status === 'pending_payment' && (
              <div className="no-print rounded-lg border border-amber-500/30 bg-amber-950/20 p-3.5 text-xs text-amber-200">
                <div className="flex items-center gap-2 font-semibold text-amber-300">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>Development Sandbox Payment Gateway</span>
                </div>
                <p className="mt-1 text-amber-200/80 leading-relaxed">
                  Your seats are transactionally locked. No real card numbers or CVV values are collected. Click below to execute idempotent server-verified demo payment confirmation.
                </p>
              </div>
            )}

            {booking.status === 'confirmed' && (
              <div className="flex items-center gap-2 text-xs text-emerald-400">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>Verified at auditorium entry via QR scan. Cancellations permitted up to 2 hours before showtime.</span>
              </div>
            )}
          </div>

          <div className="flex flex-col items-center justify-center rounded-lg border border-slate-800 bg-[#090d16] p-4">
            {qrDataUrl ? (
              <img
                src={qrDataUrl}
                alt={`QR Code for booking ${booking.bookingRef}`}
                referrerPolicy="no-referrer"
                className="h-40 w-40 rounded bg-white p-1.5"
              />
            ) : (
              <div className="flex h-40 w-40 items-center justify-center rounded bg-slate-900 text-xs text-slate-500 font-mono">
                Generating QR...
              </div>
            )}
            <span className="mt-2 font-mono text-xs font-semibold text-slate-300">
              {booking.bookingRef}
            </span>
            <span className="text-[11px] text-slate-500">Scan at Cinema Gate</span>
          </div>
        </div>

        <div className="no-print mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-5">
          <div className="flex items-center gap-3">
            {booking.status === 'confirmed' && (
              <button
                type="button"
                onClick={() => window.print()}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2 text-xs font-medium text-white hover:bg-slate-700 transition-colors whitespace-nowrap shrink-0"
              >
                <Printer className="h-4 w-4" />
                <span>Print Ticket</span>
              </button>
            )}
            {booking.status !== 'cancelled' && (
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => onCancelBooking(booking)}
                className="inline-flex items-center gap-2 rounded-lg border border-rose-500/40 bg-rose-950/30 px-4 py-2 text-xs font-medium text-rose-300 hover:bg-rose-900/40 disabled:opacity-50 transition-colors whitespace-nowrap shrink-0"
              >
                <RotateCcw className="h-4 w-4" />
                <span>Cancel &amp; Release Seats</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            {booking.status === 'pending_payment' && (
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => onConfirmPayment(booking)}
                className="rounded-lg bg-rose-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50 transition-colors whitespace-nowrap shrink-0"
              >
                {isProcessing
                  ? 'Verifying Gateway Callback...'
                  : `Authorize Demo Payment (₹${booking.totalAmount.toFixed(2)})`}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 transition-colors whitespace-nowrap shrink-0"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
