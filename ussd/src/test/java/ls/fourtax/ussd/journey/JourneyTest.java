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
        assertEquals("000123456789", registration.owner().idNumber()); assertNull(registration.businessName());
        assertEquals("VIN00000000000001", registration.vehicle().vin());
        assertNull(d.state()); assertNull(store.draft(d.crypto.digest(d.mobile)));
    }
    @Test void vendorContactCanDifferFromLoginNumberAndPinMismatchRestartsSetup() {
        d.start(); d.steps("1", "1", "3", "1", "Fresh fruit", "Market stall 2", "2", "62123456", "000123", "Mpho Example", "1", "123456", "654321");
        assertEquals("PIN_NEW", d.state().node); assertTrue(d.last.message().contains("did not match"));
        d.steps("012345", "012345");
        assertTrue(d.last.end()); assertEquals("+26662123456", backend.saved.values().iterator().next().mobileNumber());
    }
    @Test void wellnessSupportsCustomDaysTimeValidationAndSesotho() {
        d.start(); d.steps("2", "1", "2", "1", "4", "1,3,5", "25:00");
        assertEquals("FIELD:opensAt", d.state().node); assertTrue(d.last.message().contains("ha lia nepahala"));
        d.steps("08:00", "17:30", "Salon Example", "Ha Thetsane", "000456", "Mpho Example", "1", "012345", "012345");
        assertTrue(d.last.end()); assertTrue(d.last.message().contains("ngolisitsoe"));
        var registration = backend.saved.values().iterator().next();
        assertEquals(List.of("MONDAY", "WEDNESDAY", "FRIDAY"), registration.operatingSchedule().days());
        assertEquals("st", registration.source().language());
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
        d.start(); d.steps("1", "1", "1", "VIN00000000000001", "A1234", "99");
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
        d.steps("2", "5", "Ha Abia");
        assertEquals("REVIEW", d.state().node); assertEquals("Ha Abia", d.state().draft.answers.get("residence"));
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
}
