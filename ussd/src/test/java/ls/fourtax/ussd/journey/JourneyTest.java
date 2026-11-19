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
        d.transportToReview("1"); d.steps("1", "087431");
        assertFalse(store.serialized().contains("087431"));
        assertEquals("PIN_CONFIRM", d.state().node);
        d.input("087431");
        assertTrue(d.last.end()); assertTrue(d.last.message().contains("DEMO-0001"));
        var registration = backend.saved.values().iterator().next();
        assertEquals("000123456789", registration.owner().idNumber());
        assertEquals("VIN00000000000001", registration.details().get("vin"));
        assertNull(d.state()); assertNull(store.draft(d.crypto.digest(d.mobile)));
    }
    @Test void allFiveSectorsUseTheSharedContract() {
        for (String language : List.of("1", "2")) for (int sector=1; sector<=5; sector++) {
            setup(); d.start(); d.steps(language, "1", Integer.toString(sector)); d.fillToReview();
            d.steps("1", "012345", "012345");
            assertTrue(d.last.end());
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
        while (!d.state().node.equals("COLLECTION:employees")) {
            String field = d.state().node.substring(6);
            d.input(switch(field) {
                case "fullNames" -> "Mpho Example"; case "idNumber" -> "000123";
                case "location" -> "Maseru"; case "other_description" -> "-"; default -> "1";
            });
        }
        d.steps("1", "First Employee", "5", "1", "Second Employee", "1", "2");
        assertEquals("REVIEW", d.state().node);
        d.steps("1", "012345", "654321");
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
        d.fillToReview(); d.steps("1", "012345", "012345");
        assertTrue(d.last.end()); assertEquals("st", backend.saved.values().iterator().next().source().language());
    }
    @Test void loginAllowsAnotherBusinessWithoutPinCreation() {
        d.transportToReview("1"); d.steps("1", "012345", "012345");
        d.start(); d.steps("1", "2", "012345", "1"); d.vendorFields(); d.input("1");
        assertTrue(d.last.end()); assertEquals(1, backend.creations); assertEquals(2, backend.saved.size());
    }
    @Test void lostRegistrationResponseRequiresLoginAndReusesIdenticalOperationAfterResume() {
        backend.loseRegistrationReply = true;
        d.transportToReview("1"); d.steps("1", "012345", "012345");
        assertEquals("RETRY", d.state().node); assertEquals(1, backend.saved.size());
        d.input("2"); assertEquals("RETRY", d.state().node); // Ambiguous submissions cannot be edited into duplicates.
        d.input("99"); assertNull(d.state());
        d.start(); d.steps("2", "1", "1"); assertEquals("LOGIN_PIN", d.state().node);
        d.steps("012345", "1");
        assertTrue(d.last.end()); assertEquals(1, backend.creations); assertEquals(1, backend.saved.size());
        assertEquals(backend.attempts.getFirst(), backend.attempts.getLast());
    }
    @Test void unfinishedDraftResumesAndExpiredDraftCannotBeResurrected() {
        d.start(); d.steps("1", "1", "1", "1", "Mpho Example", "99");
        d.start(); d.steps("1", "1", "1"); assertEquals("FIELD:idNumber", d.state().node);
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
        d.input("88"); assertTrue(d.state().page > 0);
        int location = new NodeRouter().fields("transport").indexOf("location") + 1;
        d.steps("2", Integer.toString(location), "Ha Abia");
        assertEquals("REVIEW", d.state().node); assertEquals("Ha Abia", d.state().draft.answers.get("location"));
        d.steps("1", "012345", "012345"); assertTrue(d.last.end());
    }
    @Test void translationsContainExactlyTheSameKeysAndPreserveApostrophes() {
        var english = ResourceBundle.getBundle("messages", Locale.ENGLISH);
        var sesotho = ResourceBundle.getBundle("messages", Locale.forLanguageTag("st"));
        assertEquals(english.keySet(), sesotho.keySet());
        assertTrue(new Messages().text("en", "prompt.fullNames").contains("owner's"));
    }
    @Test void backCannotDisplayProtectedDraftAfterAuthenticationExpires() {
        backend.failure = "VALIDATION_ERROR";
        d.transportToReview("1"); d.steps("1", "012345", "012345");
        var session = d.state(); session.tokenExpiry = 0;
        store.saveSession(d.crypto.digest("test:TEST:" + d.sessionId + ":" + d.mobile), session);
        d.input("1"); assertEquals("LOGIN_PIN", d.state().node);
        d.input("0"); assertEquals("LOGIN_PIN", d.state().node);
        assertFalse(d.last.message().contains("Mpho Example"));
    }
    @Test void discardDraftStartsWithNoPreviousAnswers() {
        d.transportToReview("1"); d.input("99");
        d.start(); d.steps("1", "1", "2");
        assertEquals("SECTOR", d.state().node); assertTrue(d.state().draft.answers.isEmpty());
    }
    @Test void laterPageErrorsRemainVisibleAndReviewUsesTranslatedLabels() {
        d.transportToReview("2");
        d.input("88"); assertTrue(d.state().page > 0);
        d.input("invalid"); assertEquals("REVIEW", d.state().node); assertEquals(0, d.state().page);
        assertTrue(d.last.message().contains("ha lia nepahala"));
        var screens = new Screen(new Messages(), new NodeRouter(), settings());
        String review = String.join("\n", screens.pages(d.state()));
        assertFalse(review.contains("salary_range")); assertFalse(review.contains("{name="));
        assertTrue(review.contains("Synthetic Employee"));
    }

    @Test void oversizePayloadRejectionAllowsEditingWithoutRecreatingTheOwner() {
        backend.failure = "PAYLOAD_TOO_LARGE";
        d.transportToReview("1"); d.steps("1", "012345", "012345");
        assertEquals("RETRY", d.state().node); assertFalse(d.state().draft.mayHaveSubmitted);
        assertTrue(d.last.message().contains("Too many details"));
        d.input("2"); assertEquals("EDIT", d.state().node);
        int location = new NodeRouter().fields("transport").indexOf("location") + 1;
        d.steps(Integer.toString(location), "Maseru"); backend.failure = null; d.input("1");
        assertTrue(d.last.end()); assertEquals(1, backend.creations);
    }

}
