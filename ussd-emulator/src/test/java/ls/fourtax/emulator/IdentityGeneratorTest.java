package ls.fourtax.emulator;

import static org.junit.jupiter.api.Assertions.*;
import static ls.fourtax.emulator.Contracts.*;
import java.util.HashSet;
import org.junit.jupiter.api.Test;

class IdentityGeneratorTest {
    private final IdentityGenerator generator = new IdentityGenerator();
    @Test void generatesUniqueVodacomIdentitiesWithLeadingZeroMnc() {
        var subscribers = generator.generate(new GeneratorRequest(50, "58", "01"));
        var numbers = new HashSet<String>(); var imsis = new HashSet<String>();
        for (var subscriber : subscribers) {
            assertTrue(subscriber.mobileNumber().matches("\\+26658[0-9]{6}"));
            assertTrue(subscriber.imsi().matches("65101[0-9]{10}"));
            assertEquals("01", subscriber.mnc()); assertEquals("651", subscriber.mcc()); assertEquals("VOD", subscriber.network());
            assertTrue(numbers.add(subscriber.mobileNumber())); assertTrue(imsis.add(subscriber.imsi()));
        }
    }
    @Test void supportsAdditionalPublishedVodacomMncAndCustomTestPrefix() {
        var subscriber = generator.generate(new GeneratorRequest(1, "58", "10")).getFirst();
        assertTrue(subscriber.imsi().matches("65110[0-9]{10}"));
    }
    @Test void rejectsInvalidRangesAndUnboundedBatches() {
        assertThrows(IllegalArgumentException.class, () -> generator.generate(new GeneratorRequest(0, "58", "01")));
        assertThrows(IllegalArgumentException.class, () -> generator.generate(new GeneratorRequest(51, "58", "01")));
        assertThrows(IllegalArgumentException.class, () -> generator.generate(new GeneratorRequest(1, "62", "01")));
        assertThrows(IllegalArgumentException.class, () -> generator.generate(new GeneratorRequest(1, "58", "1")));
    }
}
