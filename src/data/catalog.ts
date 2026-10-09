import heroAuditoriumImg from '../assets/images/hero_cinema_auditorium_1791521078653.jpg';
import posterChronosImg from '../assets/images/poster_chronos_horizon_1791521096648.jpg';
import posterVelvetImg from '../assets/images/poster_velvet_nocturne_1791521110973.jpg';
import posterMonsoonImg from '../assets/images/poster_monsoon_express_1791521122726.jpg';
import posterSilentImg from '../assets/images/poster_silent_symphony_1791521135438.jpg';

export const HERO_BANNER_IMAGE = heroAuditoriumImg;

export interface MovieItem {
  id: string;
  slug: string;
  title: string;
  description: string;
  poster: string;
  genre: string;
  language: string;
  durationMinutes: number;
  releaseDate: string;
  certificate: 'U' | 'UA' | 'A';
  cast: string;
  director: string;
  status: 'now_showing' | 'coming_soon';
  isFeatured: boolean;
  rating: string;
}

export interface TheatreItem {
  id: string;
  name: string;
  city: string;
  address: string;
  amenities: string;
  screens: {
    id: string;
    name: string;
    soundSystem: string;
    totalSeats: number;
  }[];
}

export interface ShowtimeItem {
  id: string;
  movieId: string;
  theatreId: string;
  theatreName: string;
  city: string;
  screenName: string;
  soundSystem: string;
  showDate: string; // YYYY-MM-DD
  startTime: string; // HH:MM
  endTime: string; // HH:MM
  priceStandard: number;
  priceExecutive: number;
  priceRoyal: number;
  initialBookedSeats: string[];
}

export interface SeatDefinition {
  code: string;
  row: string;
  number: number;
  tier: 'standard' | 'executive' | 'royal';
  tierLabel: string;
}

export const MOVIES_CATALOG: MovieItem[] = [
  {
    id: 'movie-chronos-horizon',
    slug: 'chronos-horizon',
    title: 'Chronos Horizon',
    description:
      'When an orbital relay station near Cygnus X-1 begins receiving telemetry from forty years in the future, Commander Aarav Mehta leads a three-person deep-space crew across the event horizon.',
    poster: posterChronosImg,
    genre: 'Sci-Fi',
    language: 'English',
    durationMinutes: 154,
    releaseDate: '2026-09-18',
    certificate: 'UA',
    cast: 'Aarav Mehta, Elena Vance, Devika Rao, Marcus Sterling',
    director: 'Vikramaditya Sen',
    status: 'now_showing',
    isFeatured: true,
    rating: '9.2/10',
  },
  {
    id: 'movie-velvet-nocturne',
    slug: 'velvet-nocturne',
    title: 'Velvet Nocturne',
    description:
      'Set across rain-drenched South Mumbai jazz clubs over a single sleepless night, an acoustic forensic investigator unravels a decades-old conspiracy hidden inside an unreleased vinyl master.',
    poster: posterVelvetImg,
    genre: 'Mystery',
    language: 'Hindi',
    durationMinutes: 136,
    releaseDate: '2026-09-25',
    certificate: 'UA',
    cast: 'Kabir Bedi, Tara Sharma, Rajeev Khandelwal, Zoya Hussain',
    director: 'Rohan Sippy',
    status: 'now_showing',
    isFeatured: true,
    rating: '8.9/10',
  },
  {
    id: 'movie-monsoon-express',
    slug: 'monsoon-express',
    title: 'The Monsoon Express',
    description:
      'Aboard a heritage mountain locomotive stranded on a high stone viaduct in the Western Ghats during a torrential tempest, nine strangers must collaborate to secure the bridge before daybreak.',
    poster: posterMonsoonImg,
    genre: 'Thriller',
    language: 'Hindi',
    durationMinutes: 128,
    releaseDate: '2026-10-02',
    certificate: 'UA',
    cast: 'Neeraj Kabi, Radhika Apte,gulshan Devaiah, Tillotama Shome',
    director: 'Meghna Gulzar',
    status: 'now_showing',
    isFeatured: true,
    rating: '8.7/10',
  },
  {
    id: 'movie-silent-symphony',
    slug: 'silent-symphony',
    title: 'Silent Symphony',
    description:
      'Faced with progressive acoustic vertigo weeks before her Vienna Philharmonic debut, principal cellist Mira Deshmukh discovers a radical resonance technique that transforms how she perceives sound.',
    poster: posterSilentImg,
    genre: 'Drama',
    language: 'English',
    durationMinutes: 122,
    releaseDate: '2026-10-24',
    certificate: 'U',
    cast: 'Mira Deshmukh, Julian Hirth, Adil Hussain',
    director: 'Chaitanya Tamhane',
    status: 'coming_soon',
    isFeatured: false,
    rating: 'Pre-Release',
  },
];

export const THEATRES_CATALOG: TheatreItem[] = [
  {
    id: 'theatre-palladium-imax',
    name: 'MyBookShow Grand IMAX — Palladium',
    city: 'Mumbai',
    address: 'Senapati Bapat Marg, Lower Parel, Mumbai 400013',
    amenities: 'IMAX Dual 4K Laser · 12-Channel Sound · Luxury Recliners',
    screens: [
      { id: 'scr-1', name: 'Audi 1 IMAX Laser', soundSystem: 'IMAX 12-Channel', totalSeats: 48 },
      { id: 'scr-2', name: 'Audi 2 Premiere Gold', soundSystem: 'Dolby Atmos', totalSeats: 48 },
    ],
  },
  {
    id: 'theatre-connaught-regal',
    name: 'MyBookShow Regal Atmos — Connaught Place',
    city: 'Delhi',
    address: 'Outer Circle, Connaught Place, New Delhi 110001',
    amenities: 'Dolby Atmos · Barco RGB Laser · Valet Parking',
    screens: [
      { id: 'scr-3', name: 'Screen 1 Atmos', soundSystem: 'Dolby Atmos', totalSeats: 48 },
    ],
  },
  {
    id: 'theatre-indiranagar-luxe',
    name: 'MyBookShow Luxe — Indiranagar',
    city: 'Bengaluru',
    address: '100 Feet Road, HAL 2nd Stage, Indiranagar, Bengaluru 560038',
    amenities: '4K Christie Laser · Gourmet Dining · Acoustic Pod Seating',
    screens: [
      { id: 'scr-4', name: 'Auditorium Prime', soundSystem: 'Dolby 7.1 Surround', totalSeats: 48 },
    ],
  },
];

export const AVAILABLE_DATES = [
  { date: '2026-10-09', label: 'Fri, 09 Oct' },
  { date: '2026-10-10', label: 'Sat, 10 Oct' },
  { date: '2026-10-11', label: 'Sun, 11 Oct' },
];

export const SHOWTIMES_CATALOG: ShowtimeItem[] = [
  // Chronos Horizon
  {
    id: 'show-ch-mum-1009-1830',
    movieId: 'movie-chronos-horizon',
    theatreId: 'theatre-palladium-imax',
    theatreName: 'MyBookShow Grand IMAX — Palladium',
    city: 'Mumbai',
    screenName: 'Audi 1 IMAX Laser',
    soundSystem: 'IMAX 12-Channel',
    showDate: '2026-10-09',
    startTime: '18:30',
    endTime: '21:04',
    priceStandard: 320,
    priceExecutive: 450,
    priceRoyal: 640,
    initialBookedSeats: ['C4', 'C5', 'D4', 'D5', 'F3', 'F4'],
  },
  {
    id: 'show-ch-mum-1009-2145',
    movieId: 'movie-chronos-horizon',
    theatreId: 'theatre-palladium-imax',
    theatreName: 'MyBookShow Grand IMAX — Palladium',
    city: 'Mumbai',
    screenName: 'Audi 1 IMAX Laser',
    soundSystem: 'IMAX 12-Channel',
    showDate: '2026-10-09',
    startTime: '21:45',
    endTime: '00:19',
    priceStandard: 360,
    priceExecutive: 490,
    priceRoyal: 680,
    initialBookedSeats: ['B3', 'B4', 'E5', 'E6'],
  },
  {
    id: 'show-ch-del-1009-1915',
    movieId: 'movie-chronos-horizon',
    theatreId: 'theatre-connaught-regal',
    theatreName: 'MyBookShow Regal Atmos — Connaught Place',
    city: 'Delhi',
    screenName: 'Screen 1 Atmos',
    soundSystem: 'Dolby Atmos',
    showDate: '2026-10-09',
    startTime: '19:15',
    endTime: '21:49',
    priceStandard: 290,
    priceExecutive: 410,
    priceRoyal: 580,
    initialBookedSeats: ['D3', 'D4'],
  },
  {
    id: 'show-ch-blr-1010-2000',
    movieId: 'movie-chronos-horizon',
    theatreId: 'theatre-indiranagar-luxe',
    theatreName: 'MyBookShow Luxe — Indiranagar',
    city: 'Bengaluru',
    screenName: 'Auditorium Prime',
    soundSystem: 'Dolby 7.1 Surround',
    showDate: '2026-10-10',
    startTime: '20:00',
    endTime: '22:34',
    priceStandard: 310,
    priceExecutive: 440,
    priceRoyal: 620,
    initialBookedSeats: ['C2', 'C3', 'F5', 'F6'],
  },
  // Velvet Nocturne
  {
    id: 'show-vn-mum-1009-2015',
    movieId: 'movie-velvet-nocturne',
    theatreId: 'theatre-palladium-imax',
    theatreName: 'MyBookShow Grand IMAX — Palladium',
    city: 'Mumbai',
    screenName: 'Audi 2 Premiere Gold',
    soundSystem: 'Dolby Atmos',
    showDate: '2026-10-09',
    startTime: '20:15',
    endTime: '22:31',
    priceStandard: 280,
    priceExecutive: 390,
    priceRoyal: 560,
    initialBookedSeats: ['C5', 'C6', 'E3', 'E4'],
  },
  {
    id: 'show-vn-del-1010-1800',
    movieId: 'movie-velvet-nocturne',
    theatreId: 'theatre-connaught-regal',
    theatreName: 'MyBookShow Regal Atmos — Connaught Place',
    city: 'Delhi',
    screenName: 'Screen 1 Atmos',
    soundSystem: 'Dolby Atmos',
    showDate: '2026-10-10',
    startTime: '18:00',
    endTime: '20:16',
    priceStandard: 260,
    priceExecutive: 370,
    priceRoyal: 520,
    initialBookedSeats: ['B5', 'B6'],
  },
  // The Monsoon Express
  {
    id: 'show-me-mum-1009-1700',
    movieId: 'movie-monsoon-express',
    theatreId: 'theatre-palladium-imax',
    theatreName: 'MyBookShow Grand IMAX — Palladium',
    city: 'Mumbai',
    screenName: 'Audi 2 Premiere Gold',
    soundSystem: 'Dolby Atmos',
    showDate: '2026-10-09',
    startTime: '17:00',
    endTime: '19:08',
    priceStandard: 250,
    priceExecutive: 360,
    priceRoyal: 510,
    initialBookedSeats: ['D4', 'D5', 'D6'],
  },
  {
    id: 'show-me-blr-1009-1930',
    movieId: 'movie-monsoon-express',
    theatreId: 'theatre-indiranagar-luxe',
    theatreName: 'MyBookShow Luxe — Indiranagar',
    city: 'Bengaluru',
    screenName: 'Auditorium Prime',
    soundSystem: 'Dolby 7.1 Surround',
    showDate: '2026-10-09',
    startTime: '19:30',
    endTime: '21:38',
    priceStandard: 270,
    priceExecutive: 380,
    priceRoyal: 540,
    initialBookedSeats: ['E4', 'E5'],
  },
  // Silent Symphony
  {
    id: 'show-ss-mum-1011-1900',
    movieId: 'movie-silent-symphony',
    theatreId: 'theatre-palladium-imax',
    theatreName: 'MyBookShow Grand IMAX — Palladium',
    city: 'Mumbai',
    screenName: 'Audi 2 Premiere Gold',
    soundSystem: 'Dolby Atmos',
    showDate: '2026-10-11',
    startTime: '19:00',
    endTime: '21:02',
    priceStandard: 300,
    priceExecutive: 420,
    priceRoyal: 590,
    initialBookedSeats: ['F4', 'F5'],
  },
];

export const AUDITORIUM_ROWS: { row: string; tier: 'standard' | 'executive' | 'royal'; tierLabel: string }[] = [
  { row: 'A', tier: 'standard', tierLabel: 'Standard Front' },
  { row: 'B', tier: 'standard', tierLabel: 'Standard Front' },
  { row: 'C', tier: 'executive', tierLabel: 'Executive Prime' },
  { row: 'D', tier: 'executive', tierLabel: 'Executive Prime' },
  { row: 'E', tier: 'executive', tierLabel: 'Executive Prime' },
  { row: 'F', tier: 'royal', tierLabel: 'Royal Recliner' },
];

export function getAuditoriumSeats(): SeatDefinition[] {
  const seats: SeatDefinition[] = [];
  for (const r of AUDITORIUM_ROWS) {
    for (let num = 1; num <= 8; num++) {
      seats.push({
        code: `${r.row}${num}`,
        row: r.row,
        number: num,
        tier: r.tier,
        tierLabel: r.tierLabel,
      });
    }
  }
  return seats;
}

export function getSeatPrice(show: ShowtimeItem, tier: 'standard' | 'executive' | 'royal'): number {
  if (tier === 'royal') return show.priceRoyal;
  if (tier === 'executive') return show.priceExecutive;
  return show.priceStandard;
}
