package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.TestSupport.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class ReviewPaginationTest {
    @Test void populatedCollectionsHaveNoRedundantHeadingPageInEitherLanguage() {
        for (String language : List.of("1", "2")) for (int sector = 1; sector <= 5; sector++) {
            var d = new Driver(new MemoryStore(), new FakeBackend());
            d.start(); d.steps(language, "1", String.valueOf(sector)); d.fillToReview();
            var s = d.state();
            s.draft.collections.put("employees", List.of(Map.of("name", "Synthetic Employee", "salary_range", "1000_9999")));
            var pages = new Screen(new Messages(), new NodeRouter(), settings()).pages(s);
            String all = String.join("\n", pages);
            assertTrue(all.contains("Synthetic Employee"));
            assertFalse(all.contains(RegistrationSchema.label(s.draft.sector, "employees", s.language) + ":"));
            for (String page : pages) assertTrue(page.length() <= 160);
        }
    }
    @Test void emptyListsStayExplicitAndLongEmployeeNamesArePreserved() {
        var d = new Driver(new MemoryStore(), new FakeBackend()); d.transportToReview("1");
        var s = d.state(); s.draft.collections.put("employees", List.of());
        var screen = new Screen(new Messages(), new NodeRouter(), settings());
        assertTrue(String.join("\n", screen.pages(s)).contains("Employees and monthly salaries: 0"));
        s.draft.collections.put("employees", List.of(Map.of("name", "Synthetic".repeat(10), "salary_range", "20000_plus")));
        for (String page : screen.pages(s)) assertTrue(page.length() <= 160);
        assertTrue(String.join("", screen.pages(s)).contains("Monthly salary"));
    }
}
