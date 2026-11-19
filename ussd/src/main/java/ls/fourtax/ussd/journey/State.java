package ls.fourtax.ussd.journey;

import java.util.*;

public final class State {
    private State() {}
    public static final class Session {
        public String mobile;
        public String language = "en";
        public String node = "LANGUAGE";
        public int page;
        public String error;
        public String terminal;
        public String token;
        public String ownerId;
        public long tokenExpiry;
        public String pinDigest;
        public String pinNonce;
        public boolean editing;
        public boolean resumeAfterLogin;
        public List<String> history = new ArrayList<>();
        public Draft draft;
        public Session() {}
        public Session(String mobile) { this.mobile = mobile; }
        public void clearAuthentication() { token = null; ownerId = null; tokenExpiry = 0; clearPin(); }
        public void clearPin() { pinDigest = null; pinNonce = null; }
    }
    public static final class Draft {
        public String operationId = UUID.randomUUID().toString();
        public String sector;
        public String language = "en";
        public String node = "SECTOR";
        public Map<String, String> answers = new LinkedHashMap<>();
        public boolean authenticationStarted;
        public boolean mayHaveSubmitted;
        public String ownerId;
        public Draft() {}
    }
}
