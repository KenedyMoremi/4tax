package ls.fourtax.ussd.callback;

public record Callback(String adapter, String network, String sessionId, String mobileNumber,
        Event event, String input, String serviceCode, String requestId) {
    public enum Event { START, INPUT, ABORT }
    @Override public String toString() { return "Callback[redacted]"; }
    public record Reply(String message, boolean end) {
        @Override public String toString() { return "Reply[redacted]"; }
    }
}
