Hospital Patient Queue Management System (HPQMS)Domain Specification & Architectural BlueprintDocument Version: v0.1Status: Living SpecificationSystem Type: Healthcare Workflow & Real-Time Queue Engine1. Project VisionHPQMS is a modern Hospital Patient Queue Management System designed to govern patient movement from physical arrival through clinical consultation while ensuring patient safety, queue transparency, and operational efficiency.The system is architected to integrate with existing Hospital Management Information Systems (HMIS) and Electronic Health Record (EHR) platforms rather than replace them.┌────────────────────────────────────────────────────────┐
│               Existing Hospital EHR/HMIS               │
│         (Clinical Records, Billing, Labs, MAR)         │
└───────────────────────────┬────────────────────────────┘
                            │ API / Integration Layer
┌───────────────────────────▼────────────────────────────┐
│                         HPQMS                          │
│     (Patient Flow, Visits, Tokens, Dynamic Queues)      │
└────────────────────────────────────────────────────────┘
HPQMS focuses exclusively on patient flow, visit lifecycle management, dynamic routing, token issuance, staff station coordination, and real-time operational monitoring.2. Core PrinciplesClinical Care FirstClinical care must never be delayed by administrative intake. Patient treatment always takes priority over demographic completeness.Every Patient Is TraceableEvery patient interaction must remain linked to a single, identifiable patient record throughout its operational lifecycle.Queue History Is PermanentQueue entries represent immutable historical events. Completed, cancelled, or transferred queue records are never deleted from the database.Single Active Visit InvariantA patient may only have one ACTIVE visit at any given time. This invariant protects queue state, token generation, and departmental handoffs from data corruption.Integration Before ReplacementHPQMS complements existing hospital information systems. It does not replace Electronic Medical Records (EMRs).Security & Auditability by DesignRole-Based Access Control (RBAC), authentication, authorization, transaction logging, and strict auditability are foundational design requirements.3. Domain OverviewHPQMS manages the high-level progression of a patient through a healthcare facility:[ Patient Arrival ] ──► [ Visit Created ] ──► [ Dispatch / Route ] ──► [ Department Queue ] ──► [ Service Delivered ] ──► [ Visit Complete ]
Patient: The individual receiving care. Holds demographic and registration status.Visit: The temporal "container" for a single hospital stay or appointment.Token: The human-friendly queue identifier (e.g., W-102, E-004).Routing: The decision engine that evaluates patient state and assigns them to a department queue.Queue Entry: The active or historical record of a patient waiting for or receiving service at a specific station.4. Core Business RulesPatient RulesBR-001: A patient record may exist without complete demographic information (e.g., Kiosk intake or Emergency John Doe).BR-002: A patient may be temporarily unidentified upon arrival in critical scenarios.BR-003: Temporary patients must remain uniquely identifiable via system-generated identifiers (e.g., TEMP-YYYYMMDD-XXXX).BR-004: Identity reconciliation updates the existing temporary record. It must never create a duplicate patient entity.BR-005: A single patient entity may have many historical visits over time.BR-006: A patient may have at most one ACTIVE visit at any time.Visit RulesBR-007: Every visit belongs to exactly one patient.BR-008: Every visit is assigned a unique token upon entry creation.BR-009: Visits transition through a defined lifecycle: ACTIVE $\rightarrow$ COMPLETED or CANCELLED.Queue RulesBR-010: The routing engine dispatches visits to create QueueEntry records.BR-011: QueuePriority (CRITICAL, HIGH, NORMAL, LOW) governs ordering within a department queue.BR-012: First-In, First-Out (FIFO) applies strictly among entries of equal priority.BR-013: Completed or cancelled queue entries remain immutable for reporting and audit trails.5. Reception WorkflowThe Reception workflow covers standard walk-in intake, kiosk check-in, demographic updates, and initial department dispatch.Operational SequencePatient Arrives (Walk-In / Kiosk)
        │
        ▼
Register Patient (PatientService)
        │  ├── New Patient ──► RegistrationStatus.INCOMPLETE
        │  └── Existing Patient ──► Reuse Patient Record
        ▼
Start Visit (VisitService)
        │  ├── Verify Single Active Visit Invariant (BR-006)
        │  └── Generate Token (e.g., W-101)
        ▼
Dispatch Route (RoutingService)
        │  └── Route to Reception Queue (Status: WAITING)
        ▼
Queue Progression (QueueService)
        │  ├── WAITING  ── (Staff calls patient)
        │  ├── CALLED   ── (Patient arrives at desk)
        │  ├── IN_PROGRESS ── (Demographics/Triage completed)
        │  └── COMPLETED
        ▼
Complete Visit / Transfer
        └── VisitStage -> COMPLETED
Verified Integration Test MappingOperational StepVerified By Integration TestKey Invariant / AssertionNew Walk-in Check-Intest_walk_in_patient_registration_workflow()Initial status is INCOMPLETE; Token starts with W-Returning Patienttest_existing_patient_walk_in_workflow()Reuses patient_id; Zero duplicate patients createdConcurrent Visit Preventedtest_duplicate_active_visit_rejected()Second active visit throws HTTP 409 ConflictQueue State Machinetest_patient_queue_progression()Validates WAITING $\rightarrow$ CALLED $\rightarrow$ IN_PROGRESS $\rightarrow$ COMPLETEDVisit Finalizationtest_patient_visit_completion()VisitStage.COMPLETED set with valid completed_atVisit Cancellationtest_patient_visit_cancellation()VisitStage.CANCELLED set cleanly6. Emergency WorkflowGuiding PrincipleClinical intervention always precedes administrative completeness.In an emergency scenario, clinical staff attend to the patient immediately. Administrative details are entered via a rapid intake mechanism and reconciled once the patient is stabilized.Operational SequenceCritical Patient Arrives
        │
        ▼
Rapid John Doe Check-In
        │  ├── Skeleton Patient Created (e.g., "John Doe-ER-01")
        │  └── RegistrationStatus = INCOMPLETE
        ▼
Start Emergency Visit
        │  └── EntryType = EMERGENCY
        ▼
Direct Fast-Track Routing
        │  ├── Bypass Reception & Routine Triage
        │  ├── Route directly to Emergency Department Queue
        │  └── Priority = CRITICAL
        ▼
Immediate Resus / Clinical Treatment
        │  └── Queue Progression: WAITING -> CALLED -> IN_PROGRESS -> COMPLETED
        ▼
Demographic Reconciliation
        │  ├── Relatives / Paramedics provide identity
        │  ├── Update Patient Demographics
        │  └── RegistrationStatus = COMPLETE
        ▼
Visit Completion / Admission
7. Domain State MachinesA. Patient Registration State (RegistrationStatus) ┌──────────────┐       Demographic Intake /       ┌──────────────┐
 │  INCOMPLETE  │ ───────────────────────────────► │   COMPLETE   │
 └──────────────┘         Reconciliation           └──────────────┘
B. Visit Lifecycle (VisitStage)                 ┌──────────────┐
                 │    ACTIVE    │
                 └──────┬───────┘
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
 ┌──────────────┐              ┌──────────────┐
 │  COMPLETED   │              │  CANCELLED   │
 └──────────────┘              └──────────────┘
C. Queue Entry Lifecycle (QueueEntryStatus) ┌──────────────┐   Call    ┌──────────────┐   Start   ┌──────────────┐  Complete ┌──────────────┐
 │   WAITING    │ ────────► │    CALLED    │ ────────► │ IN_PROGRESS  │ ────────►│  COMPLETED   │
 └──────────────┘           └──────────────┘           └──────────────┘          └──────────────┘
        │                                                     │
        └─────────────────►  ┌──────────────┐  ◄──────────────┘
              Cancel        │  CANCELLED   │
                            └──────────────┘
8. Current Implementation StatusDomain Component / FeatureImplementation StatusIntegration Test CoverageAuthentication & RBAC Infrastructure✅ CompleteVerified (Unit/API)Patient Registration & Lookup✅ CompleteVerified (test_reception_workflow.py)Visit Lifecycle Engine✅ CompleteVerified (test_reception_workflow.py)Token Generation Engine✅ CompleteVerified (test_reception_workflow.py)Core Routing Service✅ CompleteVerified (test_reception_workflow.py, test_emergency_workflow.py)Queue State Machine Engine✅ CompleteVerified (test_reception_workflow.py, test_emergency_workflow.py)Reception Workflow✅ Complete100% Integration Test CoverageEmergency Workflow🟡 Active RefinementCore Dispatch VerifiedInter-Departmental Handoffs⏳ PlannedNext MilestoneAppointment Check-In & Priority Boost⏳ PlannedScheduledHMIS / EHR Integration Adapters⏳ PlannedScheduled



PHASE 1 — Display specification
        ↓
PHASE 2 — Display data contract / schemas
        ↓
PHASE 3 — DisplayService domain logic
        ↓
PHASE 4 — DisplayService tests
        ↓
PHASE 5 — Notification event model
        ↓
PHASE 6 — NotificationService
        ↓
PHASE 7 — Public display frontend
        ↓
PHASE 8 — Staff queue frontend
        ↓
PHASE 9 — Responsive testing