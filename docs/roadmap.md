# KonnectCore roadmap

This file lists planned work after the pilot-readiness fixes. Items in each section are in priority order.

## Next phase (after the MVP pilot)

### 1. Bulk actions

- Select several members and assign them to a group, change their status, archive them or export them.
- Only Admins and Managers can use bulk actions.
- Every bulk action needs a confirmation step and records a history entry for each member it changes.
- Bulk actions follow the same rules as single-record actions. For example, a bulk archive needs a reason, and a void is still blocked by active allocations.

### 2. Advanced filters

- Combined filters on members, collections and payments:
  - group
  - field officer
  - crop
  - date range
  - status
  - location
- Filters are kept in the page URL, so a filtered view can be shared as a link.
- Exports use the same filters as the list on screen.
- Filters never widen a user's access: field officers still see only the members assigned to them.

### 3. Offline field capture

- Field officers can record visits, collections and member registrations without a connection. This uses an installable web app with local storage and a queue of records waiting to sync.
- Each record gets a submission key created on the device. This builds on the existing duplicate-submission protection, so sending the same record again during sync does not create a duplicate.
- Conflicts are shown to staff for review rather than overwritten silently. Examples: the member was archived, the officer's assignment changed, or the record was already submitted.

## Deferred from the pilot-readiness UAT

- Show member history ("View changes") as readable text instead of raw data (I-8).
- Add pagination to the member, collection, farm and payment lists (I-10).
- Show an "access denied" page instead of redirecting a signed-in user to the login page (I-11).
- Limit the import file picker to CSV and XLSX files (I-12).
- Collapse the sidebar on phone-sized screens.
- Provide a downloadable member import template.
- Redirect users who are already signed in away from the login page.
- Clear or lock the Create organisation form after it succeeds, so it can't be submitted twice by accident.
- Decide whether invitations should be sent by email. Today, invitation links are only shown on screen.

## Broader accounting (outside the MVP)

The MVP only tracks settlement: which collections a payment to a member covers. These features are out of scope for the MVP:

- A general ledger, double-entry bookkeeping and a chart of accounts.
- Price schedules, deductions such as levies, loan repayments and input credit, and calculating net pay per collection.
- Batch payouts, for example one monthly mobile-money run, with reconciliation against provider statements.
- Allocating dues, contributions and savings. In the MVP these stay outside the allocation workflow.
- Approval workflows for payments, and separation of duties.
- Financial period closing, and locking edits to closed periods.
- Multi-currency support and exchange rates.
