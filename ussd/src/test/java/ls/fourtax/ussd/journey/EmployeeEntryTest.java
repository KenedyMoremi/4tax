package ls.fourtax.ussd.journey;

import static org.junit.jupiter.api.Assertions.*;
import static ls.fourtax.ussd.journey.TestSupport.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class EmployeeEntryTest {
    private Driver employeeEntry(String language, String sector) {
        var d = new Driver(new MemoryStore(), new FakeBackend());
        d.start(); d.steps(language, "1", sector);
        d.fillUntilAny(Set.of("FIELD:employees.name", "COLLECTION:employees"));
        assertEquals("FIELD:employees.name", d.state().node, "Employee capture must start with the name, without an initial collection menu");
        return d;
    }
    private void saveSession(Driver d, State.Session session) {
        d.store.saveDraft(d.crypto.digest(d.mobile), session.draft);
        d.store.saveSession(d.crypto.digest("test:TEST:" + d.sessionId + ":" + d.mobile), session);
    }
    private String allPages(Driver d) {
        return String.join("\n", new Screen(new Messages(), new NodeRouter(), settings()).pages(d.state()));
    }
    @Test void everySectorStartsWithNameThenSalaryAndOnlyThenShowsAddAnother() {
        for (String language : List.of("1", "2")) for (String sector : List.of("1", "2", "3", "4", "5")) {
            var d = employeeEntry(language, sector);
            assertEquals("FIELD:employees.name", d.state().node);
            assertTrue(d.last.message().contains(new Messages().text(d.state().language, "registration.employeeNamePrompt")));
            assertFalse(d.last.message().contains("(0)"));
            d.input("First Employee"); assertEquals("FIELD:employees.salary_range", d.state().node);
            assertTrue(allPages(d).contains("1. " + new Messages().text(d.state().language, "registration.choice.below_500")));
            assertTrue(allPages(d).contains("5. " + new Messages().text(d.state().language, "registration.choice.20000_plus")));
            d.input("5"); assertEquals("COLLECTION:employees", d.state().node);
            assertEquals(1, d.state().draft.collections.get("employees").size());
            d.input("1"); assertEquals("FIELD:employees.name", d.state().node);
            d.steps("Second Employee", "1", "2"); assertEquals("REVIEW", d.state().node);
            assertEquals(0, d.backend.creations); assertTrue(d.backend.attempts.isEmpty());
            d.steps("1", "012345", "012345"); assertTrue(d.last.end());
            var employees = d.backend.saved.values().iterator().next().employees();
            assertEquals(2, employees.size());
            assertEquals(Map.of("name", "First Employee", "salary_range", "20000_plus"), employees.getFirst());
            assertEquals(Map.of("name", "Second Employee", "salary_range", "below_500"), employees.getLast());
        }
    }
    @Test void aBusinessWithoutEmployeesCanContinueFromTheNamePrompt() {
        for (String sector : List.of("1", "2", "3", "4", "5")) {
            var d = employeeEntry("1", sector); d.input("-"); assertEquals("REVIEW", d.state().node);
            d.steps("1", "012345", "012345"); assertTrue(d.last.end());
            assertTrue(d.backend.saved.values().iterator().next().employees().isEmpty());
        }
    }
    @Test void addingAnotherEmployeeCanBeCancelledWithoutDiscardingSavedEmployees() {
        var d = employeeEntry("1", "4"); d.steps("First Employee", "2", "1", "-");
        assertEquals("REVIEW", d.state().node); assertEquals(1, d.state().draft.collections.get("employees").size());
        assertEquals("First Employee", d.state().draft.collections.get("employees").getFirst().get("name"));
    }
    @Test void backFromSalaryAllowsRenamingWithoutCreatingADuplicate() {
        var d = employeeEntry("1", "4"); d.steps("Original Name", "0");
        assertEquals("FIELD:employees.name", d.state().node);
        d.steps("Corrected Name", "3", "2"); assertEquals("REVIEW", d.state().node);
        assertEquals(1, d.state().draft.collections.get("employees").size());
        assertEquals("Corrected Name", d.state().draft.collections.get("employees").getFirst().get("name"));
    }
    @Test void editingAndClearingEmployeesReturnsDirectlyToNameCapture() {
        var d = employeeEntry("1", "4"); d.steps("First Employee", "1", "2", "2");
        int employees = new NodeRouter().fields(d.state().draft).indexOf("employees") + 1;
        d.input(Integer.toString(employees)); assertEquals("COLLECTION:employees", d.state().node);
        d.input("3"); assertEquals("FIELD:employees.name", d.state().node);
        d.steps("Replacement Employee", "4", "2"); assertEquals("REVIEW", d.state().node);
        assertEquals(1, d.state().draft.collections.get("employees").size());
        assertEquals("Replacement Employee", d.state().draft.collections.get("employees").getFirst().get("name"));
    }
    @Test void employeeNameAndSalaryStepSurviveSessionRecovery() {
        var d = employeeEntry("1", "4"); d.steps("Saved Employee", "99");
        d.start(); d.steps("1", "1", "1"); assertEquals("FIELD:employees.salary_range", d.state().node);
        d.steps("2", "2"); assertEquals("REVIEW", d.state().node);
        assertEquals("Saved Employee", d.state().draft.collections.get("employees").getFirst().get("name"));
    }
    @Test void anOldEmptyEmployeeMenuResumesAtTheNamePrompt() {
        var d = employeeEntry("1", "4"); var session = d.state();
        session.node = "COLLECTION:employees"; session.draft.node = session.node; saveSession(d, session);
        d.start(); d.steps("1", "1", "1"); assertEquals("FIELD:employees.name", d.state().node);
    }
}
