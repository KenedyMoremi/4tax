package ls.fourtax.emulator;

import static ls.fourtax.emulator.Contracts.*;
import java.security.SecureRandom;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class IdentityGenerator {
    private final SecureRandom random = new SecureRandom();
    public List<Subscriber> generate(GeneratorRequest request) {
        if (request.count() < 1 || request.count() > 50 || request.prefix() == null || !request.prefix().matches("5[0-9]")
                || !Set.of("01", "10").contains(Objects.requireNonNullElse(request.mnc(), "")))
            throw new IllegalArgumentException("Choose 1–50 subscribers, a two-digit prefix starting with 5, and MNC 01 or 10.");
        Set<String> numbers = new HashSet<>(); Set<String> identities = new HashSet<>();
        List<Subscriber> result = new ArrayList<>();
        while (result.size() < request.count()) {
            String number = "+266" + request.prefix() + digits(6);
            String imsi = "651" + request.mnc() + digits(10);
            if (numbers.contains(number) || identities.contains(imsi)) continue;
            numbers.add(number); identities.add(imsi);
            result.add(new Subscriber(UUID.randomUUID().toString(), number, imsi, "VOD", "651", request.mnc()));
        }
        return result;
    }
    private String digits(int length) {
        StringBuilder result = new StringBuilder(length);
        for (int i = 0; i < length; i++) result.append(random.nextInt(10));
        return result.toString();
    }
}
