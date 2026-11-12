# KonnectCore: Feature Scope Alignment Document

**Project:** KonnectCore Management Platform  
**Date:** 2026-11-12  
**Status:** Discovery / Scope Alignment  

---

## 1. Project Context
KonnectCore (the "Organisation OS") is transitioning from its baseline MVP to a more specialized tool for managing government-affiliated irrigation farmland and farming cooperatives. The goal is to replace paper-based systems, WhatsApp-based advisory, and unverified distribution with a centralized, audit-ready digital platform.

## 2. Detailed Feature Scope

### 2.1 Fertilizer Distribution Tracking
*   **Goal:** Prevent illegal resale of subsidized inputs by verifying needs and tracking delivery.
*   **Functionality:**
    *   New module for input requests (NPK, Organic, Seedlings).
    *   **Statuses:** `Requested` -> `Verified` (by officer) -> `Delivered` / `Partially Delivered` / `Rejected`.
    *   Audit reports for district directors to monitor distribution patterns.
*   **Technical Impact:** New `InputAllocation` model, multi-step status workflow, and filtered audit views.

### 2.2 Interactive Location Picker (Map)
*   **Goal:** Move beyond raw GPS coordinates to a visually intuitive map interface.
*   **Functionality:**
    *   Satellite map view with a draggable pin.
    *   "Use My Location" functionality for field officers.
    *   Visual confirmation of farm boundaries.
*   **Technical Impact:** Frontend integration with Leaflet/OpenStreetMap or Google Maps API; mapping of `latitude`/`longitude` to interactive UI components.

### 2.3 Planting & Harvest Coordination
*   **Goal:** Group farmers by crop readiness to coordinate shared heavy machinery (combine harvesters).
*   **Functionality:**
    *   Record specific planting dates.
    *   Automatic/Manual calculation of projected harvest dates based on crop variety.
    *   "Machinery Coordination" view: Groups farmers in the same "block" with overlapping harvest windows.
*   **Technical Impact:** Enhancement to `FarmCropSeason` model; grouping logic in the dashboard/reporting module.

### 2.4 Field Activity & Advisory Logs
*   **Goal:** Formalize monthly visit reports and pest/disease advisory.
*   **Functionality:**
    *   Extension officer-only workspace logs.
    *   Photo uploads for pest/disease identification.
    *   Structured advice fields and history tracking.
*   **Technical Impact:** Enhancement of current `FieldVisit` model or new `AdvisoryRecord` model; photo management for advisory contexts.

### 2.5 Next of Kin & Land Succession
*   **Goal:** Manage plot rights and transfers within government irrigation schemes.
*   **Functionality:**
    *   "Advanced Fields" on Member onboarding: Name, Relationship, Phone, Address of beneficiary.
    *   "Plot Transfer" workflow: Seamlessly reassign farm rights to heirs in the event of a member's death.
*   **Technical Impact:** New fields in `Member` profile; administrative workflow to update `Farm` ownership history.

### 2.6 National ID Digital Verification
*   **Goal:** Eliminate physical card handling and paper photocopies.
*   **Functionality:**
    *   Drop-down for ID Type (Voter ID, NHIS, Ghana Card).
    *   Dedicated "Camera Slots" for front and back ID photo uploads.
*   **Technical Impact:** Specific `MemberDocument` categories; UI enhancements for dual-photo uploads.

---

## 3. Scope Alignment & Technical Constraints

| Feature | Complexity | Dependencies |
| :--- | :--- | :--- |
| **Fertilizer Tracking** | Medium | User/Role permissions (Verification logic) |
| **Location Picker** | Medium | Map Provider API Key (Google/Mapbox) |
| **Harvest Dates** | High | Crop maturity metadata/lookup tables |
| **Advisory Logs** | Medium | Media storage (Photo handling) |
| **Next of Kin** | Low | Data migration (if existing members need updates) |
| **ID Verification** | Low | Encryption/Privacy considerations for PII |

---

## 4. Estimated Costing

*The following is an estimate based on development hours. Final costs depend on region, seniority, and platform hosting requirements.*

| Item | Estimated Hours | Development Cost (Est.) |
| :--- | :---: | :---: |
| Fertilizer Tracking System | 24 - 32h | $1,800 - $2,400 |
| Interactive Mapping & UI | 16 - 20h | $1,200 - $1,500 |
| Planting/Harvest Logic & Grouping | 20 - 24h | $1,500 - $1,800 |
| Advisory Logs & Photo Reports | 12 - 16h | $900 - $1,200 |
| Succession & ID Management | 10 - 14h | $750 - $1,050 |
| **Subtotal (Features)** | **82 - 106h** | **$6,150 - $7,950** |
| Project Management / QA (15%) | 12 - 16h | $900 - $1,200 |
| **Total Project Estimate** | **94 - 122h** | **$7,050 - $9,150** |

---

## 5. Timeline (Projected)
Assuming a dedicated developer, these features can be delivered over a period of **4 to 6 weeks**, including UAT (User Acceptance Testing) and deployment to the staging environment.

---
*Note: This document serves as a baseline for agreement. Changes to requirements after sign-off may impact timeline and cost.*
