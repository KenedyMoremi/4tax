package ls.fourtax.auth;

import static ls.fourtax.auth.Contracts.*;
import java.time.*;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Service
public class OwnerAuthService {
    private final JdbcTemplate db;
    private final PasswordEncoder passwords;
    private final TransactionTemplate transactions;
    private final JwtEncoder tokens;
    private final AuthSettings settings;
    private final String dummyHash;

    public OwnerAuthService(JdbcTemplate db, PasswordEncoder passwords, PlatformTransactionManager manager,
            JwtEncoder tokens, AuthSettings settings) {
        this.db = db; this.passwords = passwords; this.transactions = new TransactionTemplate(manager);
        this.tokens = tokens; this.settings = settings; this.dummyHash = passwords.encode("never-a-valid-pin");
    }

    public OwnerStatus lookup(OwnerLookup request) {
        String phone;
        try { phone = PhoneNumbers.normalize(request == null ? null : request.mobileNumber()); }
        catch (IllegalArgumentException error) { throw failure(HttpStatus.BAD_REQUEST, "INVALID_MOBILE"); }
        return new OwnerStatus(Boolean.TRUE.equals(db.queryForObject(
                "select exists(select 1 from owner_credentials where mobile_number = ?)", Boolean.class, phone)));
    }

    public TokenReply create(PinRequest request, String key) {
        String phone = phone(request); validatePin(request.pin());
        if (key == null || !key.matches("[A-Za-z0-9._:-]{1,128}"))
            throw failure(HttpStatus.BAD_REQUEST, "INVALID_IDEMPOTENCY_KEY");
        // Advisory transaction locks serialize competing creations, including before a row exists.
        UUID ownerId = transactions.execute(status -> {
            db.queryForObject("select pg_advisory_xact_lock(hashtextextended(?, 0)) is null", Boolean.class, phone);
            db.queryForObject("select pg_advisory_xact_lock(hashtextextended(?, 0)) is null", Boolean.class, "creation:" + key);
            var rows = db.query("select * from owner_credentials where mobile_number = ? or creation_key = ?",
                    (rs, row) -> new Credential(rs.getObject("id", UUID.class), rs.getString("mobile_number"),
                            rs.getString("pin_hash"), rs.getString("creation_key"), rs.getInt("failed_attempts"),
                            rs.getTimestamp("locked_until") == null ? null : rs.getTimestamp("locked_until").toInstant()), phone, key);
            if (!rows.isEmpty()) {
                Credential existing = rows.getFirst();
                if (existing.key().equals(key)) {
                    if (!existing.phone().equals(phone) || !passwords.matches(request.pin(), existing.hash()))
                        throw failure(HttpStatus.CONFLICT, "IDEMPOTENCY_CONFLICT");
                    return existing.id();
                }
                throw failure(HttpStatus.CONFLICT, "OWNER_EXISTS");
            }
            UUID id = UUID.randomUUID();
            db.update("insert into owner_credentials(id, mobile_number, pin_hash, creation_key) values (?, ?, ?, ?)",
                    id, phone, passwords.encode(request.pin()), key);
            return id;
        });
        return issue(ownerId);
    }

    public TokenReply login(PinRequest request) {
        String phone = phone(request); validatePin(request.pin());
        // Return failures from the transaction, then throw: failed-attempt updates must commit.
        LoginResult result = transactions.execute(status -> {
            var rows = db.query("select * from owner_credentials where mobile_number = ? for update",
                    (rs, row) -> new Credential(rs.getObject("id", UUID.class), rs.getString("mobile_number"),
                            rs.getString("pin_hash"), rs.getString("creation_key"), rs.getInt("failed_attempts"),
                            rs.getTimestamp("locked_until") == null ? null : rs.getTimestamp("locked_until").toInstant()), phone);
            if (rows.isEmpty()) { passwords.matches(request.pin(), dummyHash); return new LoginResult(null, "INVALID_CREDENTIALS"); }
            Credential owner = rows.getFirst();
            Instant now = Instant.now();
            if (owner.lockedUntil() != null && owner.lockedUntil().isAfter(now)) return new LoginResult(null, "PIN_LOCKED");
            if (!passwords.matches(request.pin(), owner.hash())) {
                int attempts = owner.lockedUntil() != null ? 1 : owner.attempts() + 1;
                db.update("update owner_credentials set failed_attempts = ?, locked_until = ? where id = ?", attempts,
                        attempts >= 5 ? java.sql.Timestamp.from(now.plus(Duration.ofMinutes(15))) : null, owner.id());
                return new LoginResult(null, attempts >= 5 ? "PIN_LOCKED" : "INVALID_CREDENTIALS");
            }
            db.update("update owner_credentials set failed_attempts = 0, locked_until = null where id = ?", owner.id());
            return new LoginResult(owner.id(), null);
        });
        if (result.error() != null) throw failure(result.error().equals("PIN_LOCKED") ? HttpStatus.LOCKED : HttpStatus.UNAUTHORIZED, result.error());
        return issue(result.ownerId());
    }

    private TokenReply issue(UUID ownerId) {
        Instant now = Instant.now();
        var claims = JwtClaimsSet.builder().issuer(settings.issuer()).subject(ownerId.toString())
                .audience(List.of("registration-api")).issuedAt(now).expiresAt(now.plusSeconds(900))
                .id(UUID.randomUUID().toString()).claim("scope", "businesses:create businesses:read transactions:create").claim("kind", "owner").build();
        String jwt = tokens.encode(JwtEncoderParameters.from(JwsHeader.with(SignatureAlgorithm.RS256).build(), claims)).getTokenValue();
        return new TokenReply(ownerId.toString(), jwt, "Bearer", 900);
    }

    private String phone(PinRequest request) {
        if (request == null) throw failure(HttpStatus.BAD_REQUEST, "INVALID_REQUEST");
        try { return PhoneNumbers.normalize(request.mobileNumber()); }
        catch (IllegalArgumentException e) { throw failure(HttpStatus.BAD_REQUEST, "INVALID_MOBILE"); }
    }
    private void validatePin(String pin) {
        if (pin == null || !pin.matches("[0-9]{6}")) throw failure(HttpStatus.BAD_REQUEST, "INVALID_PIN_FORMAT");
    }
    private AuthFailure failure(HttpStatus status, String code) { return new AuthFailure(status, code); }
    private record Credential(UUID id, String phone, String hash, String key, int attempts, Instant lockedUntil) {}
    private record LoginResult(UUID ownerId, String error) {}
    public static final class AuthFailure extends RuntimeException {
        final HttpStatus status; final String code;
        AuthFailure(HttpStatus status, String code) { super(code); this.status = status; this.code = code; }
    }
}
