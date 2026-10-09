/**
 * Phase 0: Payload-First Security TDD Test Suite for MyBookShow Firestore Rules
 * Verifies that all 12 "Dirty Dozen" adversarial payloads are rejected with PERMISSION_DENIED.
 */

export interface DirtyDozenTestCase {
  id: number;
  name: string;
  collectionPath: string;
  operation: 'get' | 'list' | 'create' | 'update' | 'delete';
  auth: { uid: string; email: string; email_verified: boolean } | null;
  payload?: Record<string, unknown>;
  expectedResult: 'PERMISSION_DENIED';
}

export const DIRTY_DOZEN_TEST_CASES: DirtyDozenTestCase[] = [
  {
    id: 1,
    name: 'Shadow Field Injection on UserProfile (isAdmin: true)',
    collectionPath: '/users/user_1',
    operation: 'create',
    auth: { uid: 'user_1', email: 'alice@example.com', email_verified: true },
    payload: {
      uid: 'user_1',
      displayName: 'Alice',
      preferredCity: 'Mumbai',
      isAdmin: true,
      createdAt: 'REQUEST_TIME',
      updatedAt: 'REQUEST_TIME',
    },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 2,
    name: 'Identity Spoofing on Booking Create',
    collectionPath: '/bookings/MBS-100001',
    operation: 'create',
    auth: { uid: 'attacker_uid', email: 'attacker@example.com', email_verified: true },
    payload: {
      bookingRef: 'MBS-100001',
      userId: 'victim_uid',
      showId: 'show_1',
    },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 3,
    name: 'Unverified Email Admin Spoofing',
    collectionPath: '/admins/spoof_1',
    operation: 'create',
    auth: { uid: 'spoof_1', email: 'ridhamgupta020@gmail.com', email_verified: false },
    payload: {
      uid: 'spoof_1',
      grantedAt: 'REQUEST_TIME',
    },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 4,
    name: 'Cross-User PII Read on /users/victim_uid/private/info',
    collectionPath: '/users/victim_uid/private/info',
    operation: 'get',
    auth: { uid: 'attacker_uid', email: 'attacker@example.com', email_verified: true },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 5,
    name: 'ID Poisoning (2KB junk document ID)',
    collectionPath: `/bookings/${'A'.repeat(200)}`,
    operation: 'create',
    auth: { uid: 'user_1', email: 'alice@example.com', email_verified: true },
    payload: {},
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 6,
    name: 'Unbounded Seat Array Exhaustion (50 seats in booking)',
    collectionPath: '/bookings/MBS-100002',
    operation: 'create',
    auth: { uid: 'user_1', email: 'alice@example.com', email_verified: true },
    payload: {
      bookingRef: 'MBS-100002',
      userId: 'user_1',
      seats: Array.from({ length: 50 }, (_, i) => `A${i + 1}`),
    },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 7,
    name: 'Terminal State Resurrection on Cancelled Booking',
    collectionPath: '/bookings/MBS-100003',
    operation: 'update',
    auth: { uid: 'user_1', email: 'alice@example.com', email_verified: true },
    payload: {
      status: 'confirmed',
      paymentStatus: 'paid',
      updatedAt: 'REQUEST_TIME',
    },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 8,
    name: 'Immortal Field Mutation on Booking Update (totalAmount)',
    collectionPath: '/bookings/MBS-100004',
    operation: 'update',
    auth: { uid: 'user_1', email: 'alice@example.com', email_verified: true },
    payload: {
      totalAmount: 1,
      status: 'confirmed',
      paymentStatus: 'paid',
      updatedAt: 'REQUEST_TIME',
    },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 9,
    name: 'Client Timestamp Forgery on User Creation',
    collectionPath: '/users/user_1',
    operation: 'create',
    auth: { uid: 'user_1', email: 'alice@example.com', email_verified: true },
    payload: {
      uid: 'user_1',
      displayName: 'Alice',
      preferredCity: 'Mumbai',
      createdAt: '2020-01-01T00:00:00Z',
      updatedAt: '2020-01-01T00:00:00Z',
    },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 10,
    name: 'Orphaned Booking Without Atomic Show Inventory Sync',
    collectionPath: '/bookings/MBS-100005',
    operation: 'create',
    auth: { uid: 'user_1', email: 'alice@example.com', email_verified: true },
    payload: {
      bookingRef: 'MBS-100005',
      userId: 'user_1',
      showId: 'uncommitted_show_id',
    },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 11,
    name: 'Blanket List Scraping on /bookings without userId filter',
    collectionPath: '/bookings',
    operation: 'list',
    auth: { uid: 'attacker_uid', email: 'attacker@example.com', email_verified: true },
    expectedResult: 'PERMISSION_DENIED',
  },
  {
    id: 12,
    name: 'Value Poisoning on Whitelisted Update Field',
    collectionPath: '/bookings/MBS-100006',
    operation: 'update',
    auth: { uid: 'user_1', email: 'alice@example.com', email_verified: true },
    payload: {
      status: 'INVALID_ENUM_STATUS',
      paymentStatus: 'paid',
      updatedAt: 'REQUEST_TIME',
    },
    expectedResult: 'PERMISSION_DENIED',
  },
];
