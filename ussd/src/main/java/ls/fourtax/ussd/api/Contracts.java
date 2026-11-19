package ls.fourtax.ussd.api;

import java.util.List;
import java.util.Map;

/** Local consumer contracts. The auth API is authoritative for authentication. */
public final class Contracts {
    private Contracts() {}
    public record PinRequest(String mobileNumber, String pin) {
        @Override public String toString() { return "PinRequest[redacted]"; }
    }
    public record TokenReply(String ownerId, String accessToken, String tokenType, long expiresIn) {
        @Override public String toString() { return "TokenReply[redacted]"; }
    }
    public record Owner(String idNumber, String fullNames) {}
    public record Source(String channel, String language) {}
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    public record BusinessRegistration(String sector, Owner owner, Map<String, Object> details,
            List<Map<String, String>> employees, List<Map<String, String>> routes,
            List<Map<String, String>> livestock, Source source) {
        @Override public String toString() { return "BusinessRegistration[redacted]"; }
    }
    public record RegistrationReply(String entityId, String reference) {}
    public record OwnerLookup(String mobileNumber) {
        @Override public String toString() { return "OwnerLookup[redacted]"; }
    }
    public record OwnerStatus(Boolean registered) {}
    public record BusinessSummary(String entityId, String reference, String sector, String businessName) {
        @Override public String toString() { return "BusinessSummary[redacted]"; }
    }
    public record BusinessPage(List<BusinessSummary> businesses, Integer nextPage) {
        @Override public String toString() { return "BusinessPage[redacted]"; }
    }
    public record TransactionRequest(String channel, String action, String entityId, String sector, Map<String, String> fields, String language) {
        @Override public String toString() { return "TransactionRequest[redacted]"; }
    }
    public record TransactionAction(String channel, String action, String entityId, String transactionId) {
        @Override public String toString() { return "TransactionAction[redacted]"; }
    }
    public record TransactionPreview(String action, String description, String date, String net, String tax, String total,
            String buyer, String paymentAccount, String dueDate) {
        @Override public String toString() { return "TransactionPreview[redacted]"; }
    }
    public record TransactionReply(String transactionId, String status, String reference, String summary, String result, TransactionPreview preview) {
        public TransactionReply(String transactionId, String status, String reference, String summary, String result) {
            this(transactionId, status, reference, summary, result, null);
        }
        @Override public String toString() { return "TransactionReply[redacted]"; }
    }
    public record ApiError(String code, String message, Map<String, String> fields) {}
}
