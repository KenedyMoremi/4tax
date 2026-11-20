package ls.fourtax.ussd.journey;

import static org.junit.jupiter.api.Assertions.*;
import static ls.fourtax.ussd.journey.TestSupport.*;
import java.util.*;
import ls.fourtax.ussd.callback.Callback;
import org.junit.jupiter.api.*;

class JourneyTest {
    MemoryStore store;
    FakeBackend backend;
    Driver d;
    @BeforeEach void setup() { store = new MemoryStore(); backend = new FakeBackend(); d = new Driver(store, backend); }

    @Test void transportPreservesIdsAndConsecutiveMatchingPinsAreNotDeduplicated() {
        d.transportToReview("1"); d.advance(); d.input("087431");
        assertFalse(store.serialized().contains("087431"));
        assertEquals("PIN_CONFIRM", d.state().node);
        d.input("087431");
        assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node); assertTrue(d.last.message().contains("DEMO-0001"));
        var registration = backend.saved.values().iterator().next();
        assertEquals("000123456789", registration.owner().idNumber());
        assertEquals("VIN00000000000001", registration.details().get("vin"));
        assertNull(store.draft(d.crypto.digest(d.mobile))); assertEquals("owner-token",d.state().token);
        assertTrue(d.last.message().contains("1. Main menu")); assertTrue(d.last.message().contains("0. Exit"));
        assertFalse(d.last.message().contains("8. Back"));
        d.input("1"); assertEquals("AUTH_MENU",d.state().node);
        d.input("8"); assertEquals("AUTH_MENU",d.state().node);
        d.input("0"); assertTrue(d.last.end()); assertNull(d.state());
    }
    @Test void allFiveSectorsUseTheSharedContract() {
        for (String language : List.of("1", "2")) for (int sector=1; sector<=5; sector++) {
            setup(); d.start(); d.steps(language, "1", Integer.toString(sector)); d.fillToReview();
            d.advance(); d.steps("012345", "012345");
            assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node);
            var registration = backend.saved.values().iterator().next();
            assertEquals(RegistrationSchema.sectors().get(sector-1), registration.sector());
            assertEquals("below_100", registration.details().get("turnover_range"));
            assertEquals(language.equals("1") ? "en" : "st", registration.source().language());
            assertEquals(2, registration.employees().size());
            assertEquals("below_500", registration.employees().getFirst().get("salary_range"));
            String json = tools.jackson.databind.json.JsonMapper.builder().build().writeValueAsString(registration);
            assertFalse(json.contains("\"routes\":null"));
            assertFalse(json.contains("\"livestock\":null"));
            assertFalse(json.contains("ownerId"));
        }
    }
    @Test void employeeNameThenSalaryMenuRepeatsAndCanContinue() {
        d.start(); d.steps("1", "1", "4");
        d.fillUntil("FIELD:employees.name");
        d.steps("First Employee", "5", "1", "Second Employee", "1", "9");
        assertEquals("REVIEW", d.state().node);
        d.advance(); d.steps("012345", "654321");
        assertEquals("PIN_NEW", d.state().node);
        d.steps("012345", "012345");
        var staff = backend.saved.values().iterator().next().employees();
        assertEquals(2, staff.size()); assertEquals("20000_plus", staff.getFirst().get("salary_range"));
        assertEquals("Second Employee", staff.getLast().get("name"));
        assertEquals("below_500", staff.getLast().get("salary_range"));
    }
    @Test void invalidTimeDoesNotAdvanceAndSesothoSessionIsPreserved() {
        d.start(); d.steps("2", "1", "2", "1", "Mpho Example", "000123", "1", "25:00");
        // Hours precede common location fields in the shared form metadata.
        assertEquals("FIELD:opens_at", d.state().node);
        d.fillToReview(); d.advance(); d.steps("012345", "012345");
        assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node); assertEquals("st", backend.saved.values().iterator().next().source().language());
    }
    @Test void loginAllowsAnotherBusinessWithoutPinCreation() {
        d.transportToReview("1"); d.advance(); d.steps("012345", "012345");
        d.start(); d.steps("1", "012345", "1"); d.vendorFields(); d.advance();
        assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node); assertEquals(1, backend.creations); assertEquals(2, backend.saved.size());
    }
    @Test void loggedInBusinessFlowsSkipOwnerPromptsReviewAndEditingInBothLanguages() {
        for (String language : List.of("1", "2")) for (int sector=1; sector<=5; sector++) {
            setup(); backend.pins.put(d.mobile,"012345");
            d.start(); d.steps(language,"012345","1",Integer.toString(sector));
            assertFalse(d.state().draft.collectOwnerDetails);
            d.choose("1"); assertFalse(Set.of("FIELD:fullNames","FIELD:idNumber").contains(d.state().node));
            d.input("8"); d.choose("1"); d.fillToReview();
            assertFalse(d.state().draft.answers.containsKey("fullNames"));
            assertFalse(d.state().draft.answers.containsKey("idNumber"));
            String review=String.join("\n",d.screens().pages(d.state()));
            assertFalse(review.contains(RegistrationSchema.label(d.state().draft.sector,"fullNames",d.state().language)));
            d.lastPage(); d.input("1");
            assertFalse(new NodeRouter().fields(d.state().draft).contains("fullNames"));
            assertFalse(new NodeRouter().fields(d.state().draft).contains("idNumber"));
            d.input("8"); assertEquals("REVIEW",d.state().node); d.advance();
            assertEquals("REG_DONE",d.state().node); assertFalse(d.last.end());
            var registration=backend.saved.values().iterator().next(); assertNull(registration.owner());
            assertFalse(tools.jackson.databind.json.JsonMapper.builder().build().writeValueAsString(registration).contains("\"owner\""));
            assertEquals(0,backend.creations); assertNotNull(d.state().token);
            d.input("1"); assertEquals("AUTH_MENU",d.state().node);
            d.input("0"); assertTrue(d.last.end());
        }
    }
    @Test void successExitEndsTheSessionAndCannotSubmitAgain() {
        d.transportToReview("1"); d.advance(); d.steps("012345","012345");
        assertEquals("REG_DONE",d.state().node); d.input("9");
        assertEquals(1,backend.attempts.size()); assertEquals("REG_DONE",d.state().node);
        d.input("0"); assertTrue(d.last.end()); assertNull(d.state());
    }
    @Test void loggedInDraftResumesWithoutOwnerPromptsAndRetriesTheSamePayload() {
        backend.pins.put(d.mobile,"012345"); d.start(); d.steps("1","012345","1","4","1","Maseru","0");
        d.start(); d.steps("1","012345","1","9");
        assertFalse(d.state().draft.collectOwnerDetails); d.fillToReview();
        backend.loseRegistrationReply=true; d.advance(); assertEquals("RETRY",d.state().node);
        var request=backend.saved.values().iterator().next(); assertNull(request.owner());
        d.input("0"); d.start(); d.steps("1","012345","1","9");
        assertEquals("REG_DONE",d.state().node); assertEquals(1,backend.saved.size());
        assertEquals(backend.attempts.getFirst(),backend.attempts.getLast());
        assertEquals(request,backend.saved.values().iterator().next());
    }
    @Test void oldAuthenticatedDraftPausedAtOwnerDetailsSkipsThosePromptsOnResume() {
        backend.pins.put(d.mobile,"012345"); d.start(); d.steps("1","012345","1","4","1");
        var session=d.state(); session.draft.collectOwnerDetails=true;
        session.node="FIELD:idNumber"; session.draft.node=session.node;
        session.draft.answers.put("fullNames","Previously entered owner");
        store.saveDraft(d.crypto.digest(d.mobile),session.draft);
        store.saveSession(d.crypto.digest("test:TEST:"+d.sessionId+":"+d.mobile),session);
        d.input("0"); d.start(); d.steps("1","012345","1","9");
        assertEquals("FIELD:location",d.state().node); assertFalse(d.state().draft.collectOwnerDetails);
        assertFalse(d.state().draft.answers.containsKey("fullNames"));
        d.fillToReview(); d.advance(); assertEquals("REG_DONE",d.state().node);
        assertNull(backend.saved.values().iterator().next().owner());
    }
    @Test void lostRegistrationResponseRequiresLoginAndReusesIdenticalOperationAfterResume() {
        backend.loseRegistrationReply = true;
        d.transportToReview("1"); d.advance(); d.steps("012345", "012345");
        assertEquals("RETRY", d.state().node); assertEquals(1, backend.saved.size());
        d.input("2"); assertEquals("RETRY", d.state().node); // Ambiguous submissions cannot be edited into duplicates.
        d.input("0"); assertNull(d.state());
        d.start(); d.steps("2"); assertEquals("LOGIN_PIN", d.state().node);
        d.steps("012345", "1", "9");
        assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node); assertEquals(1, backend.creations); assertEquals(1, backend.saved.size());
        assertEquals(backend.attempts.getFirst(), backend.attempts.getLast());
    }
    @Test void unfinishedDraftResumesAndExpiredDraftCannotBeResurrected() {
        d.start(); d.steps("1", "1", "1", "1", "Mpho Example", "0");
        d.start(); d.steps("1", "1", "9"); assertEquals("FIELD:idNumber", d.state().node);
        store.advance(901); d.input("000123"); assertTrue(d.last.end()); assertTrue(d.last.message().contains("expired"));
        d.start(); d.steps("1", "1"); assertEquals("SECTOR", d.state().node);
    }
    @Test void stableRequestIdIsDeduplicatedButIdenticalInputAtNextNodeIsNot() {
        d.start();
        var first = d.send(Callback.Event.INPUT, "1", "same-request");
        var replay = d.send(Callback.Event.INPUT, "1", "same-request");
        assertEquals(first, replay); assertEquals("MAIN", d.state().node);
        d.send(Callback.Event.INPUT, "1", "different-request"); assertEquals("SECTOR", d.state().node);
    }
    @Test void reviewPaginationAndEditingRetainRequiredInformation() {
        d.transportToReview("1");
        assertTrue(d.last.message().contains("(1/"));
        d.input("9"); assertTrue(d.state().page > 0);
        d.editField("location"); d.input("Ha Abia");
        assertEquals("REVIEW", d.state().node); assertEquals("Ha Abia", d.state().draft.answers.get("location"));
        d.advance(); d.steps("012345", "012345"); assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node);
    }
    @Test void translationsContainExactlyTheSameKeysAndPreserveApostrophes() {
        var english = ResourceBundle.getBundle("messages", Locale.ENGLISH);
        var sesotho = ResourceBundle.getBundle("messages", Locale.forLanguageTag("st"));
        assertEquals(english.keySet(), sesotho.keySet());
        assertTrue(new Messages().text("en", "registration.employeeNamePrompt").contains("employee"));
    }
    @Test void backCannotDisplayProtectedDraftAfterAuthenticationExpires() {
        backend.failure = "VALIDATION_ERROR";
        d.transportToReview("1"); d.advance(); d.steps("012345", "012345");
        var session = d.state(); session.tokenExpiry = 0;
        store.saveSession(d.crypto.digest("test:TEST:" + d.sessionId + ":" + d.mobile), session);
        d.input("1"); assertEquals("LOGIN_PIN", d.state().node);
        d.input("8"); assertEquals("LOGIN_PIN", d.state().node);
        assertFalse(d.last.message().contains("Mpho Example"));
    }
    @Test void discardDraftStartsWithNoPreviousAnswers() {
        d.transportToReview("1"); d.input("0");
        d.start(); d.steps("1", "1", "2");
        assertEquals("SECTOR", d.state().node); assertTrue(d.state().draft.answers.isEmpty());
    }
    @Test void laterPageErrorsRemainVisibleAndReviewUsesTranslatedLabels() {
        d.transportToReview("2");
        d.input("9"); assertTrue(d.state().page > 0);
        d.input("invalid"); assertEquals("REVIEW", d.state().node); assertEquals(0, d.state().page);
        assertTrue(d.last.message().contains("ha lia nepahala"));
        var screens = new Screen(new Messages(), new NodeRouter(), settings());
        String review = String.join("\n", screens.pages(d.state()));
        assertFalse(review.contains("salary_range")); assertFalse(review.contains("{name="));
        assertTrue(review.contains("Synthetic Employee"));
    }

    @Test void oversizePayloadRejectionAllowsEditingWithoutRecreatingTheOwner() {
        backend.failure = "PAYLOAD_TOO_LARGE";
        d.transportToReview("1"); d.advance(); d.steps("012345", "012345");
        assertEquals("RETRY", d.state().node); assertFalse(d.state().draft.mayHaveSubmitted);
        assertTrue(d.last.message().contains("Too many details"));
        d.lastPage(); d.input("1"); assertEquals("EDIT", d.state().node);
        d.choose(Integer.toString(new NodeRouter().fields(d.state().draft).indexOf("location")+1));
        d.input("Maseru"); backend.failure = null; d.advance();
        assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node); assertEquals(1, backend.creations);
    }

}
