package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.TestSupport.*;
import static ls.fourtax.ussd.api.Contracts.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class TransactionJourneyTest {
    Driver login(String sector, String language) {
        var backend = new FakeBackend(); var d = new Driver(new MemoryStore(), backend);
        backend.pins.put(d.mobile, "001234");
        backend.ownedBusinesses.add(new BusinessSummary("business-1", "4TAX-TEST0001", sector, "Test business"));
        d.start(); d.input(language);
        assertEquals("LOGIN_PIN", d.state().node); assertFalse(d.last.message().contains("Register"));
        d.input("001234"); assertEquals("AUTH_MENU", d.state().node);
        return d;
    }
    void capture(Driver d) {
        for (String field : TransactionJourney.fields(d.state().transaction.business.sector())) {
            assertEquals("TX_FIELD:"+field, d.state().node);
            d.input(switch(field) {
                case "route" -> "Maseru to Roma";
                case "passengers" -> "10 adults";
                case "fareCost" -> "M20 per passenger";
                case "service" -> "Haircut and styling";
                case "serviceCost" -> "M200 for the service";
                case "goods" -> "2 bags of produce";
                case "totalValue" -> "M200 total";
                case "paymentDetails" -> "paid in cash";
                case "buyer" -> "-";
                default -> throw new AssertionError(field);
            });
        }
        assertEquals("TX_REVIEW", d.state().node);
    }
    @Test void allFiveSectorJourneysInBothLanguagesUseFreeTextAndExplicitPosting() {
        for (String language : List.of("1", "2")) for (String sector : RegistrationSchema.sectors()) {
            var d = login(sector, language); d.input("2"); capture(d);
            assertTrue(d.backend.transactionRequests.isEmpty()); assertTrue(d.backend.postedTransactions.isEmpty());
            d.input("1"); assertEquals("TX_PREVIEW", d.state().node); assertTrue(d.backend.postedTransactions.isEmpty());
            var request = d.backend.transactionRequests.values().iterator().next();
            assertEquals(sector, request.sector()); assertEquals("business-1", request.entityId());
            assertEquals("N/A", request.fields().get("buyer")); assertEquals("paid in cash", request.fields().get("paymentDetails"));
            assertEquals(language.equals("1") ? "en" : "st", request.language());
            d.input("1"); assertEquals("TX_DONE", d.state().node); assertEquals(1, d.backend.postedTransactions.size());
            assertEquals(d.backend.transactionAttempts.getFirst(), d.backend.transactionAttempts.getLast());
            assertEquals(0, d.backend.creations);
        }
    }
    @Test void unknownOwnerCanRegisterButLookupFailureNeverMeansUnregistered() {
        var d = new Driver(new MemoryStore(), new FakeBackend()); d.start(); d.input("1");
        assertEquals("MAIN", d.state().node); assertTrue(d.last.message().contains("Register business"));
        d = new Driver(new MemoryStore(), new FakeBackend()); d.backend.lookupFailure = "SERVICE_UNAVAILABLE";
        d.start(); d.input("1"); assertEquals("ENTRY_RETRY", d.state().node); assertFalse(d.last.message().contains("Register"));
        d.backend.lookupFailure = null; d.backend.pins.put(d.mobile,"001234"); d.input("1"); assertEquals("LOGIN_PIN", d.state().node);
    }
    @Test void ownerWithSeveralBusinessesSelectsAnEntityAndCanPage() {
        var d = login("transport","1");
        for (int i=2;i<=6;i++) d.backend.ownedBusinesses.add(new BusinessSummary("business-"+i, "4TAX-TEST000"+i, "retail", "Shop "+i));
        d.input("2"); assertEquals("TX_BUSINESS",d.state().node); assertEquals(5,d.state().businesses.size());
        d.input("6"); assertEquals(2,d.state().businessPage); assertEquals(1,d.state().businesses.size());
        d.input("1"); assertEquals("TX_FIELD:goods", d.state().node); assertEquals("business-6",d.state().transaction.business.entityId());
    }
    @Test void timeoutsKeepFrozenInputsAndOriginalOperationForProposalAndConfirmation() {
        var d = login("transport","1"); d.input("2"); capture(d); d.backend.loseTransactionReply=true;
        d.input("1"); assertEquals("TX_RETRY",d.state().node); String key = d.state().transaction.operationId;
        d.input("0"); assertEquals("TX_RETRY",d.state().node); assertTrue(d.state().transaction.frozen);
        d.input("1"); assertEquals("TX_PREVIEW",d.state().node);
        d.backend.loseTransactionReply=true; d.input("1"); assertEquals("TX_RETRY",d.state().node);
        assertEquals("confirm", d.state().transaction.action); assertEquals(1,d.backend.postedTransactions.size());
        d.input("1"); assertEquals("TX_DONE",d.state().node); assertEquals(1,d.backend.postedTransactions.size());
        assertTrue(d.backend.transactionAttempts.stream().allMatch(key::equals));
    }
    @Test void validationAllowsEditingWhileAnUnconfirmedRequestDoesNot() {
        var d = login("services","2"); d.input("2"); capture(d);
        d.backend.transactionFailure="CLARIFICATION_REQUIRED"; String original=d.state().transaction.operationId;
        d.input("1"); assertEquals("TX_REVIEW",d.state().node); assertFalse(d.state().transaction.frozen);
        assertNotEquals(original,d.state().transaction.operationId);
        d.steps("2","2","M300 total"); assertEquals("TX_REVIEW",d.state().node);
        assertEquals("M300 total",d.state().transaction.fields.get("serviceCost"));
        d.backend.transactionFailure=null; d.input("1"); d.input("2");
        assertEquals("AUTH_MENU",d.state().node); assertTrue(d.backend.postedTransactions.isEmpty());
    }
    @Test void expiredAuthenticationIsRequiredBeforeShowingOrPostingTransactionDetails() {
        var d = login("retail","1"); d.input("2"); capture(d);
        var state=d.state(); state.tokenExpiry=0;
        d.store.saveSession(d.crypto.digest("test:TEST:"+d.sessionId+":"+d.mobile),state);
        d.input("1"); assertEquals("LOGIN_PIN",d.state().node); assertFalse(d.last.message().contains("produce"));
        assertTrue(d.backend.transactionRequests.isEmpty());
        d.input("001234"); assertEquals("TX_REVIEW",d.state().node); d.input("1"); assertEquals("TX_PREVIEW",d.state().node);
    }
    @Test void emptyBusinessListDoesNotGuessASectorAndBackDoesNotExposeRegistrationToKnownOwners() {
        var d=login("retail","1"); d.backend.ownedBusinesses.clear(); d.input("2");
        assertEquals("TX_EMPTY",d.state().node); assertNull(d.state().transaction);
        d.input("0"); assertEquals("AUTH_MENU",d.state().node); d.input("0");
        assertFalse(d.last.message().contains("Register business"));
    }
    @Test void inputValidationAndBackPreserveCapturedTextAndScreenLimits() {
        var d=login("transport","2"); d.input("2");
        d.input(" "); assertEquals("TX_FIELD:route",d.state().node);
        d.steps("Maseru to Roma","10 adults","0"); assertEquals("TX_FIELD:passengers",d.state().node);
        assertEquals("Maseru to Roma",d.state().transaction.fields.get("route"));
        d.steps("10 adults","M20 each","paid in cash","-");
        var screen = new Screen(new Messages(),new NodeRouter(),settings());
        for (String page:screen.pages(d.state())) assertTrue(page.length()<=160);
    }
    @Test void interruptedConfirmationCanBeResumedOnlyAfterLoginWithoutPostingAgain() {
        var d=login("retail","1"); d.input("2"); capture(d); d.input("1");
        d.backend.loseTransactionReply=true; d.input("1"); assertEquals("TX_RETRY",d.state().node);
        String key=d.state().transaction.operationId; d.input("99");
        d.start(); d.input("2"); assertEquals("LOGIN_PIN",d.state().node); d.steps("001234","2");
        assertEquals("TX_RESUME",d.state().node); assertFalse(d.last.message().contains("Discard"));
        d.steps("1","1"); assertEquals("TX_DONE",d.state().node);
        assertEquals(1,d.backend.postedTransactions.size()); assertEquals(key,d.backend.transactionAttempts.getLast());
    }
    @Test void staleInputCannotConfirmAProposalThatWasNotShownInThatSession() {
        var d=login("retail","1"); d.input("2"); capture(d);
        var stale=d.state(); d.input("1"); assertEquals("TX_PREVIEW",d.state().node);
        d.store.saveSession(d.crypto.digest("test:TEST:"+d.sessionId+":"+d.mobile),stale);
        d.input("1"); assertEquals("TX_PREVIEW",d.state().node); assertTrue(d.backend.postedTransactions.isEmpty());
        assertEquals("tx.changed",d.state().error);
        d.input("1"); assertEquals("TX_DONE",d.state().node);
        d.input("2"); d.input("0"); assertNotEquals("TX_PREVIEW",d.state().node);
    }
    @Test void aLostSuccessScreenCanRecoverTheReceiptRatherThanStartAnotherSale() {
        var d=login("retail","1"); d.input("2"); capture(d); d.steps("1","1");
        assertEquals("TX_DONE",d.state().node); d.input("99");
        d.start(); d.steps("1","001234","2"); assertEquals("TX_DONE",d.state().node);
        assertEquals(1,d.backend.transactionRequests.size()); assertEquals(1,d.backend.postedTransactions.size());
        d.input("1"); assertEquals("TX_FIELD:goods",d.state().node);
    }
}
