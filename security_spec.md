# Security Specification: MyBookShow (Phase 0 Payload-First Security TDD)

## 1. Data Invariants

1. **Default-Deny Catch-All**: No unlisted collection or document path can ever be read or written (`match /{document=**} { allow read, write: if false; }`).
2. **Verified Identity Invariant**: All write operations and private reads require `request.auth != null && request.auth.token.email_verified == true`.
3. **PII Split-Collection Invariant**: User PII (`email`, `phone`) is strictly isolated in `/users/{userId}/private/{docId}` (`docId == 'info'`). Only the owner (`request.auth.uid == userId`) or a verified admin (`isAdmin()`) may read or write it, and the parent `/users/{userId}` document must exist and belong to `userId` (Master Gate + Atomicity Guarantee via `get()` / `getAfter()`).
4. **Booking Ownership & Relational Sync Invariant**: A `/bookings/{bookingId}` document can only be created if `incoming().userId == request.auth.uid`, the referenced `/shows/{showId}` exists or is atomically written in the same transaction (`existsAfter(/databases/$(database)/documents/shows/$(incoming().showId))`), and `getAfter(/databases/$(database)/documents/shows/$(incoming().showId)).data.lastBookedBy == request.auth.uid`.
5. **Terminal State Locking**: Once a `/bookings/{bookingId}` document reaches `status == 'cancelled'`, it is locked in a terminal state and cannot be updated by non-admin users.
6. **Query Enforcer Invariant**: `allow list` on `/bookings/{bookingId}` strictly enforces `resource.data.userId == request.auth.uid` (no blanket `isSignedIn()` reads).

---

## 2. The "Dirty Dozen" Adversarial Payloads

1. **Payload 1 (Shadow Field Injection on UserProfile)**:
   `{ "uid": "user_1", "displayName": "Alice", "preferredCity": "Mumbai", "isAdmin": true, "createdAt": "<SERVER_TIME>", "updatedAt": "<SERVER_TIME>" }` -> Rejected by `hasOnly()`.
2. **Payload 2 (Identity Spoofing on Booking Create)**:
   `{ "bookingRef": "MBS-100001", "userId": "victim_uid", ... }` by `attacker_uid` -> Rejected by `data.userId == request.auth.uid`.
3. **Payload 3 (Unverified Email Admin Spoofing)**:
   Auth token `{ uid: "spoof_1", email: "ridhamgupta020@gmail.com", email_verified: false }` attempting admin write -> Rejected by `request.auth.token.email_verified == true`.
4. **Payload 4 (Cross-User PII Read on `/users/victim_uid/private/info`)**:
   Authenticated `attacker_uid` attempting `get` on `/users/victim_uid/private/info` -> Rejected by `request.auth.uid == userId || isAdmin()`.
5. **Payload 5 (ID Poisoning / 2KB Document ID)**:
   Creating `/bookings/<2000-char-junk-id>` -> Rejected by `isValidId(bookingId)`.
6. **Payload 6 (Unbounded Seat Array Exhaustion)**:
   Creating `/bookings/MBS-100002` with `seats` array of 50 elements -> Rejected by `data.seats.size() >= 1 && data.seats.size() <= 10`.
7. **Payload 7 (Terminal State Resurrection on Cancelled Booking)**:
   Updating `/bookings/MBS-100003` where `existing().status == 'cancelled'` back to `'confirmed'` -> Rejected by Terminal State Gate (`existing().status != 'cancelled'`).
8. **Payload 8 (Immortal Field Mutation on Booking Update)**:
   Updating `/bookings/MBS-100004` to change `totalAmount` or `bookingRef` during status update -> Rejected by `affectedKeys().hasOnly(...)` and immortal field checks.
9. **Payload 9 (Client Timestamp Forgery)**:
   Creating `/users/user_1` with `createdAt: Timestamp(2020, 1, 1)` instead of `request.time` -> Rejected by `incoming().createdAt == request.time`.
10. **Payload 10 (Orphaned Booking Without Show Inventory Sync)**:
    Creating `/bookings/MBS-100005` where `/shows/nonexistent_show` does not exist after batch commit -> Rejected by `existsAfter(/databases/$(database)/documents/shows/$(incoming().showId))`.
11. **Payload 11 (Blanket List Scraping on `/bookings`)**:
    Querying `collection(db, 'bookings')` without `where('userId', '==', request.auth.uid)` -> Rejected by `resource.data.userId == request.auth.uid`.
12. **Payload 12 (Value Poisoning on Whitelisted Update Field)**:
    Updating `/bookings/MBS-100006` with `{ status: "HACKED_STATE", updatedAt: request.time }` -> Rejected by `isValidBooking(incoming())` wrapping the update block.
