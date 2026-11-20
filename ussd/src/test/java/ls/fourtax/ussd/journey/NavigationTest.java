package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.TestSupport.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import ls.fourtax.ussd.callback.Callback;
import org.junit.jupiter.api.Test;

class NavigationTest {
    Driver registration(String language,String sector) {
        var d=new Driver(new MemoryStore(),new FakeBackend()); d.start(); d.steps(language,"1",sector); return d;
    }
    void persist(Driver d,State.Session s) {
        if(s.draft!=null && s.draft.meaningful()) d.store.saveDraft(d.crypto.digest(d.mobile),s.draft);
        d.store.saveSession(d.crypto.digest("test:TEST:"+d.sessionId+":"+d.mobile),s);
    }
    @Test void allRenderedControlsAreSingleDigitsAndActionsStayOnTheirOwnLines() {
        for(String language:List.of("1","2")) for(int sector=1;sector<=5;sector++) {
            var d=registration(language,Integer.toString(sector));
            d.fillToReview();
            for(var page:d.screens().layout(d.state())) {
                assertTrue(page.text().length()<=160);
                assertFalse(page.text().matches("(?s).*\\n[0-9]{2,}\\. .*"));
                for(String key:page.commands().keySet()) assertTrue(key.matches("[0-9]"));
                assertFalse(page.text().contains("enter -"));
            }
        }
    }
    @Test void numericAnswersEightZeroAndNineDoNotLoseTheirMeaning() {
        var d=registration("1","5"); d.input("2"); d.fillUntil("FIELD:farmland_count");
        d.input("00"); assertEquals("FIELD:livestock.animal_type",d.state().node);
        assertEquals("0",d.state().draft.answers.get("farmland_size")); assertEquals("",d.state().draft.answers.get("farmland_unit"));
        assertFalse(d.last.message().contains("7. Skip")); d.steps("Sheep","9");
        assertEquals("9",d.state().draft.collections.get("livestock").getFirst().get("number"));
        d.steps("1","Cattle","08"); assertEquals("8",d.state().draft.collections.get("livestock").getLast().get("number"));
        d.steps("9","7"); assertEquals("REVIEW",d.state().node); d.advance(); d.steps("001234","001234");
        var request=d.backend.saved.values().iterator().next(); assertEquals("",request.details().get("farmland_unit"));
        assertEquals("0",request.details().get("farmland_size"));
    }
    @Test void farmlandIsRequiredForFarmingAndPositiveLandRequiresAUnit() {
        var d=registration("2","5"); d.input("1"); d.fillUntil("FIELD:farmland_count");
        d.input("00"); assertEquals("FIELD:farmland_count",d.state().node);
        d.steps("08","9"); assertEquals("FIELD:farmland_unit",d.state().node);
        assertFalse(d.last.message().contains("7. ")); d.input("7"); assertEquals("FIELD:farmland_unit",d.state().node);
        d.input("1"); assertEquals("8",d.state().draft.answers.get("farmland_count"));
        assertEquals("9",d.state().draft.answers.get("farmland_size"));
    }
    @Test void daytimeHoursSkipOvernightAndSevenStillSelectsSunday() {
        var d=registration("1","1"); d.fillUntil("FIELD:working_days"); d.input("7");
        assertEquals("Sunday",d.state().draft.answers.get("working_days"));
        d.steps("08:00","17:00"); assertEquals("FIELD:location",d.state().node); assertEquals("false",d.state().draft.answers.get("overnight"));
        d.input("8"); assertEquals("FIELD:closes_at",d.state().node); d.input("07:00"); assertEquals("FIELD:overnight",d.state().node);
        d.input("1"); assertEquals("FIELD:opens_at",d.state().node); d.steps("18:00","06:00","9");
        assertEquals("true",d.state().draft.answers.get("overnight")); assertEquals("FIELD:location",d.state().node);
    }
    @Test void emptyCollectionsStartAtTheFirstFieldAndRequiredOnesCannotBeSkipped() {
        var d=registration("1","1"); d.fillUntil("FIELD:routes.origin");
        assertFalse(d.last.message().contains("Clear")); assertFalse(d.last.message().contains("7. Skip"));
        d.steps("Maseru","Roma","08"); assertEquals("COLLECTION:routes",d.state().node);
        assertEquals("8",d.state().draft.collections.get("routes").getFirst().get("price"));
        assertTrue(d.last.message().contains("9. Continue")); d.input("9");
        assertEquals("FIELD:employees.name",d.state().node); assertTrue(d.last.message().contains("7. Skip")); d.input("7"); assertEquals("REVIEW",d.state().node);
    }
    @Test void pinConfirmationBackReturnsToNewPinAndClearsDigest() {
        var d=registration("1","4"); d.fillToReview(); d.advance(); d.input("001234"); assertNotNull(d.state().pinDigest);
        d.input("8"); assertEquals("PIN_NEW",d.state().node); assertNull(d.state().pinDigest); assertNull(d.state().pinNonce);
        d.steps("000008","000008"); assertTrue(d.last.end());
    }
    @Test void editMenusHavePageLocalChoicesAndBackMovesOnePageAtATime() {
        var d=registration("1","1"); d.fillToReview(); d.lastPage(); int last=d.state().page;
        assertTrue(last>1); d.input("8"); assertEquals(last-1,d.state().page); d.lastPage(); d.input("1");
        assertEquals("EDIT",d.state().node); d.choose(Integer.toString(new NodeRouter().fields(d.state().draft).indexOf("employees")+1));
        assertEquals("COLLECTION:employees",d.state().node);
    }
    @Test void oldSessionsEndBeforeReinterpretingTheirInputsAndRetainDrafts() {
        var d=registration("1","4"); d.fillToReview(); var s=d.state(); String operation=s.draft.operationId;
        s.navigationVersion=0; persist(d,s);
        String oldKey=d.crypto.digest("test:TEST:"+d.sessionId+":"+d.mobile)+":"+d.crypto.digest("old");
        d.store.cache(oldKey,"{\"message\":\"Old cached screen\",\"end\":false}");
        d.send(Callback.Event.INPUT,"0","old"); assertTrue(d.last.end()); assertTrue(d.last.message().contains("Navigation has changed"));
        assertEquals(operation,d.store.draft(d.crypto.digest(d.mobile)).operationId);
        d.start(); d.steps("1","1","9"); assertEquals("REVIEW",d.state().node);
    }
    @Test void untouchedRegistrationAndAutoSelectedBusinessDoNotOfferRecovery() {
        var d=registration("1","1"); d.input("0"); assertNull(d.store.draft(d.crypto.digest(d.mobile)));
        d.start(); d.steps("1","1"); assertEquals("SECTOR",d.state().node);
        var tx=new TransactionJourneyTest().login("retail","1"); tx.input("2"); tx.input("0");
        assertNull(tx.store.transaction(tx.crypto.digest(tx.mobile))); tx.start(); tx.steps("1","001234","2");
        assertEquals("TX_FIELD:goods",tx.state().node);
    }
    @Test void noBackOrExitIsAdvertisedOrAcceptedAtPinLogin() {
        var d=new TransactionJourneyTest().login("retail","1"); d.input("0"); d.start(); d.input("1");
        assertEquals("LOGIN_PIN",d.state().node); assertFalse(d.last.message().contains("8.")); assertFalse(d.last.message().contains("0."));
        d.input("8"); assertEquals("LOGIN_PIN",d.state().node); d.input("0"); assertEquals("LOGIN_PIN",d.state().node);
    }
    @Test void changingFromNoLandToFarmingCollectsLandSizeAndUnitBeforeReview() {
        var d=registration("1","5"); d.input("2"); d.fillUntil("FIELD:farmland_count");
        d.steps("00","Sheep","12","9","7"); assertEquals("REVIEW",d.state().node);
        d.editField("activity"); d.input("1"); assertEquals("FIELD:farmland_count",d.state().node);
        d.input("2"); assertEquals("FIELD:farmland_size",d.state().node);
        d.steps("3.5","2"); assertEquals("REVIEW",d.state().node); assertEquals("acres",d.state().draft.answers.get("farmland_unit"));
    }
    @Test void changingActivityToLivestockCollectsAnAnimalBeforeReview() {
        var d=registration("1","5"); d.fillToReview(); var s=d.state();
        s.draft.collections.put("livestock",new ArrayList<>()); s.draft.answers.put("livestock","0"); persist(d,s);
        d.editField("activity"); d.input("2"); assertEquals("FIELD:livestock.animal_type",d.state().node);
        assertFalse(d.last.message().contains("7. Skip")); d.steps("Cattle","3","9"); assertEquals("REVIEW",d.state().node);
    }
    @Test void fullCollectionsHideAddAndNavigationDoesNotExtendDraftLifetime() {
        var d=registration("1","4"); d.fillToReview(); var s=d.state();
        var rows=new ArrayList<Map<String,String>>(); for(int i=0;i<50;i++) rows.add(Map.of("name","Employee "+i,"salary_range","below_500"));
        s.draft.collections.put("employees",rows); s.node="COLLECTION:employees"; persist(d,s);
        assertFalse(d.screens().render(s).contains("Add another")); d.input("1"); assertEquals("COLLECTION:employees",d.state().node);
        d.input("9"); ((MemoryStore)d.store).advance(899); d.input("9"); d.input("invalid"); ((MemoryStore)d.store).advance(2);
        d.input("9"); assertTrue(d.last.end()); assertNull(d.store.draft(d.crypto.digest(d.mobile)));
    }
}
