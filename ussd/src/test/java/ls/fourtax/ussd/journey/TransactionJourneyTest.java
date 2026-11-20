package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.TestSupport.*;
import static ls.fourtax.ussd.api.Contracts.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class TransactionJourneyTest {
    Driver login(String sector,String language) {
        var d=new Driver(new MemoryStore(),new FakeBackend()); d.backend.pins.put(d.mobile,"001234");
        d.backend.ownedBusinesses.add(new BusinessSummary("business-1","4TAX-TEST0001",sector,"Test business"));
        d.start(); d.input(language); assertEquals("LOGIN_PIN",d.state().node);
        assertFalse(d.last.message().contains("Register")); d.input("001234"); return d;
    }
    void capture(Driver d) {
        for(String field:TransactionJourney.fields(d.state().transaction.business.sector())) {
            assertEquals("TX_FIELD:"+field,d.state().node);
            d.input(switch(field) {
                case "route" -> "Maseru to Roma"; case "passengers" -> "10 adults";
                case "fareCost" -> "M20 per passenger"; case "service" -> "Haircut and styling";
                case "serviceCost" -> "M200 for the service"; case "goods" -> "2 bags of produce";
                case "totalValue" -> "M200 total"; case "paymentDetails" -> "paid in cash";
                case "buyer" -> "7"; default -> throw new AssertionError(field);
            });
        }
    }
    @Test void allFiveSectorJourneysInBothLanguagesPrepareOnePreviewAndRequirePostingConfirmation() {
        for(String language:List.of("1","2")) for(String sector:RegistrationSchema.sectors()) {
            var d=login(sector,language); d.input("2"); capture(d);
            assertEquals("TX_PREVIEW",d.state().node); assertEquals(1,d.backend.transactionRequests.size());
            assertTrue(d.backend.postedTransactions.isEmpty());
            var request=d.backend.transactionRequests.values().iterator().next();
            assertEquals(sector,request.sector()); assertEquals("business-1",request.entityId());
            assertEquals("N/A",request.fields().get("buyer")); assertEquals("paid in cash",request.fields().get("paymentDetails"));
            assertEquals(language.equals("1")?"en":"st",request.language());
            while(d.state().page<d.screens().pages(d.state()).size()-1) {
                assertFalse(d.last.message().contains("9. Confirm and post")); d.input("9");
                assertTrue(d.backend.postedTransactions.isEmpty());
            }
            d.input("9"); assertEquals("TX_DONE",d.state().node); assertEquals(1,d.backend.postedTransactions.size());
            assertEquals(d.backend.transactionAttempts.getFirst(),d.backend.transactionAttempts.getLast()); assertEquals(0,d.backend.creations);
        }
    }
    @Test void unknownOwnerCanRegisterButLookupFailureNeverMeansUnregistered() {
        var d=new Driver(new MemoryStore(),new FakeBackend()); d.start(); d.input("1"); assertEquals("MAIN",d.state().node);
        d=new Driver(new MemoryStore(),new FakeBackend()); d.backend.lookupFailure="SERVICE_UNAVAILABLE";
        d.start(); d.input("1"); assertEquals("ENTRY_RETRY",d.state().node);
        d.backend.lookupFailure=null; d.backend.pins.put(d.mobile,"001234"); d.input("1"); assertEquals("LOGIN_PIN",d.state().node);
    }
    @Test void severalBusinessesUseSingleDigitPagingAndBack() {
        var d=login("transport","1");
        for(int i=2;i<=6;i++) d.backend.ownedBusinesses.add(new BusinessSummary("business-"+i,"4TAX-TEST000"+i,"retail","Shop "+i));
        d.input("2"); assertEquals(5,d.state().businesses.size()); d.advance(); assertEquals(2,d.state().businessPage);
        d.input("8"); assertEquals(1,d.state().businessPage); d.advance(); d.input("1");
        assertEquals("TX_FIELD:goods",d.state().node); assertEquals("business-6",d.state().transaction.business.entityId());
    }
    @Test void timeoutsFreezeInputsAndKeepOriginalKeyForProposalAndConfirmation() {
        var d=login("transport","1"); d.input("2"); d.backend.loseTransactionReply=true; capture(d);
        assertEquals("TX_RETRY",d.state().node); String key=d.state().transaction.operationId;
        assertFalse(d.last.message().contains("8. Back")); d.input("8"); assertEquals("TX_RETRY",d.state().node);
        d.advance(); assertEquals("TX_PREVIEW",d.state().node);
        d.backend.loseTransactionReply=true; d.advance(); assertEquals("TX_RETRY",d.state().node);
        assertEquals("confirm",d.state().transaction.action); d.advance(); assertEquals("TX_DONE",d.state().node);
        assertEquals(1,d.backend.postedTransactions.size()); assertTrue(d.backend.transactionAttempts.stream().allMatch(key::equals));
    }
    @Test void clarificationAllowsEditingAndAutomaticRepreview() {
        var d=login("services","2"); d.input("2"); String original=d.state().transaction.operationId;
        d.backend.transactionFailure="CLARIFICATION_REQUIRED"; capture(d);
        assertEquals("TX_EDIT",d.state().node); assertFalse(d.state().transaction.frozen); assertNotEquals(original,d.state().transaction.operationId);
        d.backend.transactionFailure=null; d.choose("2"); d.input("M300 total"); assertEquals("TX_PREVIEW",d.state().node);
        assertEquals("M300 total",d.state().transaction.fields.get("serviceCost"));
        d.lastPage(); d.input("2"); assertEquals("AUTH_MENU",d.state().node); assertTrue(d.backend.postedTransactions.isEmpty());
    }
    @Test void editingCancelsOldPreviewBeforeCreatingARevisedOperation() {
        var d=login("services","1"); d.input("2"); capture(d); String original=d.state().transaction.operationId;
        d.lastPage(); d.input("1"); assertEquals("TX_EDIT",d.state().node); assertNotEquals(original,d.state().transaction.operationId);
        assertEquals("M200 for the service",d.state().transaction.fields.get("serviceCost"));
        d.choose("2"); d.input("M350 total"); assertEquals("TX_PREVIEW",d.state().node);
        assertEquals(2,d.backend.transactionRequests.size()); assertTrue(d.backend.postedTransactions.isEmpty()); d.advance();
        assertEquals(1,d.backend.postedTransactions.size());
    }
    @Test void lostCancellationRetainsEditIntentUntilResumeConfirmsTheResult() {
        var d=login("retail","1"); d.input("2"); capture(d); String original=d.state().transaction.operationId;
        d.lastPage(); d.backend.loseTransactionReply=true; d.input("1"); assertEquals("TX_RETRY",d.state().node);
        assertTrue(d.state().transaction.editAfterCancel); assertEquals(original,d.state().transaction.operationId);
        d.input("0"); d.start(); d.steps("1","001234","2"); assertEquals("TX_RESUME",d.state().node);
        d.advance(); assertEquals("TX_EDIT",d.state().node); assertFalse(d.state().transaction.editAfterCancel);
        assertEquals("2 bags of produce",d.state().transaction.fields.get("goods")); assertTrue(d.backend.postedTransactions.isEmpty());
    }
    @Test void expiredAuthenticationPrecedesShowingOrPostingDetails() {
        var d=login("retail","1"); d.input("2"); capture(d); d.lastPage(); var s=d.state(); s.tokenExpiry=0;
        d.store.saveSession(d.crypto.digest("test:TEST:"+d.sessionId+":"+d.mobile),s);
        d.input("9"); assertEquals("LOGIN_PIN",d.state().node); assertFalse(d.last.message().contains("produce"));
        assertTrue(d.backend.postedTransactions.isEmpty()); d.input("001234"); assertEquals("TX_PREVIEW",d.state().node);
        assertEquals(0,d.state().page); d.advance(); assertEquals("TX_DONE",d.state().node);
    }
    @Test void emptyListHasOneReturnToMenuAndDoesNotGuessASector() {
        var d=login("retail","1"); d.backend.ownedBusinesses.clear(); d.input("2"); assertEquals("TX_EMPTY",d.state().node);
        assertFalse(d.last.message().contains("Main menu")); d.input("8"); assertEquals("AUTH_MENU",d.state().node);
    }
    @Test void invalidInputsAndBackPreserveCapturedText() {
        var d=login("transport","2"); d.input("2"); d.input(" "); assertEquals("TX_FIELD:route",d.state().node);
        d.steps("Maseru to Roma","10 adults","8"); assertEquals("TX_FIELD:passengers",d.state().node);
        assertEquals("Maseru to Roma",d.state().transaction.fields.get("route")); d.steps("08","M20 each","paid in cash","7");
        assertEquals("08",d.state().transaction.fields.get("passengers"));
        for(String page:d.screens().pages(d.state())) assertTrue(page.length()<=160);
    }
    @Test void interruptedConfirmationResumesWithOneActionWithoutPostingAgain() {
        var d=login("retail","1"); d.input("2"); capture(d); d.backend.loseTransactionReply=true; d.advance();
        assertEquals("TX_RETRY",d.state().node); String key=d.state().transaction.operationId; d.input("0");
        d.start(); d.steps("2","001234","2"); assertEquals("TX_RESUME",d.state().node);
        assertFalse(d.last.message().contains("Discard")); d.advance(); assertEquals("TX_DONE",d.state().node);
        assertEquals(1,d.backend.postedTransactions.size()); assertEquals(key,d.backend.transactionAttempts.getLast());
    }
    @Test void staleInputCannotConfirmAPreviewNotShownInThatSession() {
        var d=login("retail","1"); d.input("2"); capture(d); var stale=d.state(); stale.node="TX_FIELD:buyer";
        d.store.saveSession(d.crypto.digest("test:TEST:"+d.sessionId+":"+d.mobile),stale);
        d.input("9"); assertEquals("TX_PREVIEW",d.state().node); assertTrue(d.backend.postedTransactions.isEmpty());
        assertEquals("tx.changed",d.state().error); d.advance(); assertEquals("TX_DONE",d.state().node);
    }
    @Test void lostSuccessScreenRecoversReceiptInsteadOfStartingAnotherSale() {
        var d=login("retail","1"); d.input("2"); capture(d); d.advance(); assertEquals("TX_DONE",d.state().node); d.input("0");
        d.start(); d.steps("1","001234","2"); assertEquals("TX_DONE",d.state().node);
        assertEquals(1,d.backend.transactionRequests.size()); assertEquals(1,d.backend.postedTransactions.size());
        d.input("1"); assertEquals("TX_FIELD:goods",d.state().node);
    }
    @Test void expiredConfirmationRetiresOldProposalBeforeOfferingRepreview() {
        var d=login("retail","1"); d.input("2"); capture(d); String original=d.state().transaction.operationId;
        d.backend.expiredConfirmation=true; d.advance(); assertEquals("TX_EDIT",d.state().node);
        assertNotEquals(original,d.state().transaction.operationId); assertEquals("tx.expired",d.state().error);
        assertTrue(d.backend.postedTransactions.isEmpty()); d.advance(); assertEquals("TX_PREVIEW",d.state().node);
        assertEquals(2,d.backend.transactionRequests.size()); assertTrue(d.backend.postedTransactions.isEmpty());
    }
    @Test void editingAnAlreadyPostedProposalRecoversReceiptWithoutAReplacementSale() {
        var d=login("retail","1"); d.input("2"); capture(d); String original=d.state().transaction.operationId;
        d.backend.postedTransactions.add(original); d.lastPage(); d.input("1"); assertEquals("TX_DONE",d.state().node);
        assertEquals(1,d.backend.postedTransactions.size()); assertEquals(1,d.backend.transactionRequests.size());
    }
}
