package ls.fourtax.ussd.journey;

import static org.junit.jupiter.api.Assertions.*;
import static ls.fourtax.ussd.journey.TestSupport.*;
import java.util.*;
import ls.fourtax.ussd.api.Contracts.BusinessRegistration;
import org.junit.jupiter.api.Test;

class OtherDescriptionTest {
    private Driver driver() { return new Driver(new MemoryStore(), new FakeBackend()); }
    private String otherOption(String sector) { return sector.equals("4") ? "5" : "3"; }
    private String nextPrice(String sector) { return sector.equals("5") ? "FIELD:selling_price_range" : "FIELD:purchase_price_range"; }
    private void throughTurnover(Driver d, String language, String sector, String type) {
        d.start(); d.steps(language, "1", sector, type, "Synthetic Owner", "0000123456", "Maseru", "1");
    }
    private void saveSession(Driver d, State.Session session) {
        d.store.saveDraft(d.crypto.digest(d.mobile), session.draft);
        d.store.saveSession(d.crypto.digest("test:TEST:" + d.sessionId + ":" + d.mobile), session);
    }
    private String screenText(Driver d) {
        return String.join("\n", new Screen(new Messages(), new NodeRouter(), settings()).pages(d.state()));
    }

    @Test void allListedTypesSkipOtherAfterTurnoverInBothLanguages() {
        for (String language : List.of("1", "2")) for (String sector : List.of("3", "4", "5")) {
            int listed = sector.equals("4") ? 4 : 2;
            for (int type = 1; type <= listed; type++) {
                var d = driver(); throughTurnover(d, language, sector, Integer.toString(type));
                assertEquals(nextPrice(sector), d.state().node);
                d.input("8"); assertEquals("FIELD:turnover_range", d.state().node);
                d.input("1"); assertEquals(nextPrice(sector), d.state().node);
                d.fillToReview();
                assertFalse(new NodeRouter().fields(d.state().draft).contains("other_description"));
                d.lastPage(); d.input("1"); assertFalse(screenText(d).contains("Other")); d.input("8");
                assertEquals(0, d.backend.creations); assertTrue(d.backend.attempts.isEmpty());
                d.advance(); d.steps("012345", "012345"); assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node);
                assertEquals("", d.backend.saved.values().iterator().next().details().get("other_description"));
            }
        }
    }
    @Test void selectingOtherRequiresADescriptionAndDoesNotOfferSkip() {
        for (String language : List.of("1", "2")) for (String sector : List.of("3", "4", "5")) {
            var d = driver(); throughTurnover(d, language, sector, otherOption(sector));
            assertEquals("FIELD:other_description", d.state().node);
            assertFalse(d.last.message().contains(" - "));
            for (String invalid : List.of("-", " ")) {
                d.input(invalid); assertEquals("FIELD:other_description", d.state().node);
                assertTrue(d.last.message().contains(new Messages().text(d.state().language, "error.otherDescriptionRequired")));
            }
            d.input("Synthetic other activity"); assertEquals(nextPrice(sector), d.state().node);
            d.fillToReview(); assertTrue(new NodeRouter().fields(d.state().draft).contains("other_description"));
            assertTrue(screenText(d).contains("Synthetic other activity"));
            d.advance(); d.steps("012345", "012345"); assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node);
            assertEquals("Synthetic other activity", d.backend.saved.values().iterator().next().details().get("other_description"));
        }
    }
    @Test void editingCategoryAsksForOtherDescriptionAndClearsItWhenChangingBack() {
        for (String language : List.of("1", "2")) for (String sector : List.of("3", "4", "5")) {
            var d = driver(); throughTurnover(d, language, sector, "1"); d.fillToReview();
            d.lastPage(); d.steps("1", "1", otherOption(sector)); assertEquals("FIELD:other_description", d.state().node);
            d.input("Temporary other description"); assertEquals("REVIEW", d.state().node);
            d.lastPage(); d.steps("1", "1", "1"); assertEquals("REVIEW", d.state().node);
            assertEquals("", d.state().draft.answers.get("other_description"));
            assertFalse(screenText(d).contains("Temporary other description"));
            assertFalse(new NodeRouter().fields(d.state().draft).contains("other_description"));
        }
    }
    @Test void resumingAnOldUnnecessaryDescriptionScreenAdvancesToTheNextRelevantField() {
        for (String sector : List.of("3", "4", "5")) {
            var d = driver(); throughTurnover(d, "1", sector, "1");
            var session = d.state(); session.node = "FIELD:other_description"; session.draft.node = session.node;
            session.draft.answers.put("other_description", "Legacy irrelevant text"); saveSession(d, session);
            d.start(); d.steps("1", "1", "9");
            assertEquals(nextPrice(sector), d.state().node);
            assertEquals("", d.state().draft.answers.get("other_description"));
        }
    }
    @Test void backDoesNotReopenAnInactiveDescriptionFromOldSessionHistory() {
        var d = driver(); throughTurnover(d, "1", "4", "1");
        var session = d.state(); session.history.add("FIELD:other_description"); saveSession(d, session);
        d.input("8"); assertEquals("FIELD:turnover_range", d.state().node);
    }
    @Test void ambiguousLegacySubmissionsRetainTheirExactPayloadOnRetry() {
        var d = driver(); d.backend.loseRegistrationReply = true;
        throughTurnover(d, "1", "4", "1"); d.fillToReview(); d.advance(); d.steps("012345", "012345");
        assertEquals("RETRY", d.state().node);
        var session = d.state(); String operation = session.draft.operationId;
        var original = d.backend.saved.get(operation);
        var details = new LinkedHashMap<>(original.details()); details.put("other_description", "Legacy irrelevant text");
        var legacy = new BusinessRegistration(original.sector(), original.owner(), details, original.employees(), original.routes(), original.livestock(), original.source());
        d.backend.saved.put(operation, legacy); session.draft.answers.put("other_description", "Legacy irrelevant text"); saveSession(d, session);
        d.input("0"); d.start(); d.steps("1", "012345", "1", "9");
        assertFalse(d.last.end()); assertEquals("REG_DONE",d.state().node); assertEquals(legacy, d.backend.saved.get(operation));
        assertEquals(d.backend.attempts.getFirst(), d.backend.attempts.getLast()); assertEquals(1, d.backend.creations);
    }
    @Test void protectedDraftIsNotRewrittenBeforeItsOwnerLogsIn() {
        var d = driver(); throughTurnover(d, "1", "4", "1");
        var session = d.state(); session.node = "RESUME";
        session.draft.ownerId = "owner-1"; session.draft.authenticationStarted = true;
        session.draft.answers.put("other_description", "Protected legacy text"); saveSession(d, session);
        d.input("9"); assertEquals("LOGIN_PIN", d.state().node);
        assertEquals("Protected legacy text", d.store.draft(d.crypto.digest(d.mobile)).answers.get("other_description"));
    }

}
