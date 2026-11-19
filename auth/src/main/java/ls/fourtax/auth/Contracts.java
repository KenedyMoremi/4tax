package ls.fourtax.auth;

import java.util.Map;
import java.util.Set;

public final class Contracts {
    private Contracts() {}
    public record PinRequest(String mobileNumber, String pin) {
        @Override public String toString() { return "PinRequest[redacted]"; }
    }
    public record TokenReply(String ownerId, String accessToken, String tokenType, long expiresIn) {
        @Override public String toString() { return "TokenReply[redacted]"; }
    }
    public record ApiError(String code, String message, Map<String, String> fields) {
        public ApiError(String code, String message) { this(code, message, Map.of()); }
    }
    public record ClientRequest(String applicationName, Set<String> scopes) {}
    public record ClientReply(String clientId, String clientSecret, String tokenEndpoint, Set<String> scopes) {
        @Override public String toString() { return "ClientReply[redacted]"; }
    }
}
