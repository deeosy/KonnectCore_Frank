This is a comprehensive implementation plan broken down into phases. Since KonnectCore is a mobile-responsive web application, all features must be implemented with a "Mobile-First" UI approach—prioritizing 44px tap targets, legible font sizes on small screens, and efficient media handling (since field users often work on limited data).

Implementation Roadmap

┌────────┬─────────────────────────┬────────────────────────────────────────────────┐
│ Phase  │          Focus          │               Features Included                │
├────────┼─────────────────────────┼────────────────────────────────────────────────┤
│ Phase  │ Data Integrity &        │ ID Verification, Next of Kin/Succession        │
│ 1      │ Onboarding              │                                                │
├────────┼─────────────────────────┼────────────────────────────────────────────────┤
│ Phase  │ Field Operations        │ Location Picker (Map), Field Activity &        │
│ 2      │                         │ Advisory Logs                                  │
├────────┼─────────────────────────┼────────────────────────────────────────────────┤
│ Phase  │ Platform Logistics      │ Fertilizer Distribution Tracking, Harvest      │
│ 3      │                         │ Coordination                                   │
└────────┴─────────────────────────┴────────────────────────────────────────────────┘

---

Phase 1: Onboarding & Member Data Enhancement

Goal: Secure the integrity of member profiles and identification.

1. National ID Digital Verification:
   - Data Model: Update MemberDocument to include document_type choices (Voter ID, NHIS, Ghana Card).
   - UI: Update the Member onboarding form to include dual-image upload fields (Front/Back ID) for Field Officers.
   - Validation: Ensure these documents are tagged in the audit trail as "ID Verification".
2. Next of Kin & Land Succession:
   - Data Model: Add NextOfKin fields (name, phone, relationship, address) to the Member model (or as an OneToOneField relation for cleaner data).
   - Workflow: Implement a "Transfer Ownership" workflow on the Farm model. This should link the original member record to a successor member record to maintain historical chain-of-custody.

Phase 2: Field Operations

Goal: Improve the daily utility of the platform for Field Officers.

1. Interactive Location Picker:
   - Frontend: Integrate a light, mobile-friendly mapping library (e.g., Leaflet.js with OpenStreetMap tiles).
   - UI: Add a "Map View" toggle on the farm creation form.
   - Logic: Implement a "Set from Current Location" button that grabs GPS via the browser's navigator.geolocation API, updates the map pin, and populates hidden latitude/longitude fields in the Django form.
2. Field Activity & Advisory Logs:
   - Data Model: Create an AdvisoryRecord model linked to FieldVisit or Member.
   - UI: Design a new "Field Activity" workspace (restricted to Field Officers) that allows logging observations and uploading photos.
   - Workflow: Add a "Supervisor Review" flag on records, enabling managers to approve or comment on advice given by officers.

Phase 3: Platform Logistics

Goal: Implement the most complex business logic and grouping features.

1. Fertilizer Distribution Tracking:
   - Data Model: Create an InputAllocation model with a status workflow (Requested, Verified, Delivered, etc.).
   - Workflow: Add "Input Allocation" capability to the Field Officer dashboard.
   - Reports: Build a "Distribution Audit" report for district directors, showing total allocations vs. deliveries by region/group.
2. Planting & Harvest Coordination:
   - Logic: Add a grouping helper method to the FarmCropSeason model that queries farmers by crop and expected_harvest_date (within a range, e.g., ±7 days).
   - UI: Create a "Shared Machinery Coordination" dashboard that highlights groups of farmers ready for harvesting in the same vicinity, allowing officers to coordinate machine hiring.

---

Key Technical Considerations for Web-Responsive Field Work

1. Offline/Sync Strategy:
   - Since this is a web app, implement a Service Worker to cache core assets (CSS/JS) and the map tiles for offline viewing.
   - Ensure all forms use the submission_key pattern (which you already use) to prevent duplicate submissions when connectivity is unstable.
2. Photo Management:
   - Field-captured photos can be large. Implement Client-Side Resizing (using browser canvas API) before the upload to save data for field officers and reduce server storage costs.
3. Security & PII:
   - ID photos (National ID) and Next-of-Kin data are Sensitive PII. Ensure these models inherit from OrganisationOwnedModel (as you have done) and review Django permissions to ensure only Authorized staff can view sensitive ID images.
4. Testing Requirements:
   - Because KonnectCore has a baseline of 326+ tests, every new model/workflow must include a corresponding test suite (Unit tests for business logic, Integration tests for forms) to prevent regressions in the existing multi-tenancy rules.

How to Start

I recommend we start with Phase 1 (ID Verification and Next of Kin). They are the least risky changes, help us verify our database migration workflow, and provide immediate value to the client.

Shall we start by outlining the schema changes for Phase 1?