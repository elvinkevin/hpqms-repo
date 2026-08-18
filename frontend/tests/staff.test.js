import { describe, expect, it, beforeEach, vi } from "vitest";

import {
    getActionStates,
    getPatientLabel,
    getQueueTokenLabel,
    getActionStatesForTest,
} from "../js/staff.js";


describe("Staff Dashboard", () => {

    beforeEach(() => {
        vi.clearAllMocks();
    });


    /* ======================================================================
       Queue / Patient Labels
       ====================================================================== */

    describe("queue token labels", () => {

        it("uses the visit token number when available", () => {

            const entry = {
                sequence_number: 12,
                visit: {
                    token_number: "W-112",
                },
            };

            expect(
                getQueueTokenLabel(entry)
            ).toBe("W-112");
        });


        it("falls back to the sequence number", () => {

            const entry = {
                sequence_number: 12,
                visit: {},
            };

            expect(
                getQueueTokenLabel(entry)
            ).toBe("#12");
        });

    });


    describe("patient labels", () => {

        it("returns the patient's full name", () => {

            const entry = {
                visit: {
                    patient: {
                        first_name: "John",
                        last_name: "Doe",
                    },
                },
            };

            expect(
                getPatientLabel(entry)
            ).toBe("John Doe");
        });


        it("uses the temporary identifier when no name exists", () => {

            const entry = {
                visit: {
                    patient: {
                        first_name: "",
                        last_name: "",
                        temporary_identifier: "TEMP-20260816-0001",
                    },
                },
            };

            expect(
                getPatientLabel(entry)
            ).toBe(
                "Temp ID: TEMP-20260816-0001"
            );
        });


        it("uses the national ID as a fallback", () => {

            const entry = {
                visit: {
                    patient: {
                        first_name: "",
                        last_name: "",
                        national_id: "12345678",
                    },
                },
            };

            expect(
                getPatientLabel(entry)
            ).toBe("ID: 12345678");
        });


        it("returns Unknown patient when patient data is missing", () => {

            expect(
                getPatientLabel({})
            ).toBe("Unknown patient");

        });

    });


    /* ======================================================================
       Queue Action Ownership
       ====================================================================== */

    describe("queue action states", () => {

        const currentUser = {
            staff_id: "STAFF-001",
        };


        it("allows an unassigned waiting patient to be called", () => {

            const entry = {
                status: "WAITING",
                assigned_staff_id: null,
            };

            expect(
                getActionStates(entry, currentUser)
            ).toEqual({
                call: true,
                start: false,
                noShow: false,
                complete: false,
            });

        });


        it("does not allow calling an already assigned patient", () => {

            const entry = {
                status: "WAITING",
                assigned_staff_id: "STAFF-002",
            };

            expect(
                getActionStatesForTest(entry, currentUser)
            ).toEqual({
                call: false,
                start: false,
                noShow: false,
                complete: false,
            });

        });


        it("allows the owning staff member to start a called patient", () => {

            const entry = {
                status: "CALLED",
                assigned_staff_id: "STAFF-001",
            };

            expect(
                getActionStatesForTest(entry, currentUser)
            ).toEqual({
                call: false,
                start: true,
                noShow: true,
                complete: false,
            });

        });


        it("does not allow another staff member to start a called patient", () => {

            const entry = {
                status: "CALLED",
                assigned_staff_id: "STAFF-002",
            };

            expect(
                getActionStatesForTest(entry, currentUser)
            ).toEqual({
                call: false,
                start: false,
                noShow: false,
                complete: false,
            });

        });


        it("allows the owning staff member to complete an in-progress patient", () => {

            const entry = {
                status: "IN_PROGRESS",
                assigned_staff_id: "STAFF-001",
            };

            expect(
                getActionStatesForTest(entry, currentUser)
            ).toEqual({
                call: false,
                start: false,
                noShow: false,
                complete: true,
            });

        });


        it("does not allow another staff member to complete an in-progress patient", () => {

            const entry = {
                status: "IN_PROGRESS",
                assigned_staff_id: "STAFF-002",
            };

            expect(
                getActionStatesForTest(entry, currentUser)
            ).toEqual({
                call: false,
                start: false,
                noShow: false,
                complete: false,
            });

        });

    });

});