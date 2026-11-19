package ls.fourtax.auth;

import static ls.fourtax.auth.Contracts.*;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.*;
import org.springframework.http.*;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.server.authorization.client.*;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.web.bind.annotation.*;

/** Public application provisioning during the prototype phase. */
@RestController
public class ClientProvisioningController {
    private static final Set<String> ALLOWED_SCOPES = Set.of("owners:create", "owners:login");
    private final RegisteredClientRepository clients;
    private final PasswordEncoder passwords;
    private final AuthSettings settings;
    private final SecureRandom random = new SecureRandom();

    public ClientProvisioningController(RegisteredClientRepository clients, PasswordEncoder passwords, AuthSettings settings) {
        this.clients = clients; this.passwords = passwords; this.settings = settings;
    }

    @PostMapping("/api/v1/clients")
    ResponseEntity<?> provision(@RequestBody ClientRequest request) {
        if (request.applicationName() == null || request.applicationName().isBlank() || request.applicationName().length() > 100
                || request.scopes() == null || request.scopes().isEmpty()
                || request.scopes().stream().anyMatch(scope -> scope == null || !ALLOWED_SCOPES.contains(scope)))
            return ResponseEntity.badRequest().body(new ApiError("INVALID_CLIENT", "Supply an application name and supported scopes."));
        String clientId = "app_" + UUID.randomUUID().toString().replace("-", "");
        byte[] entropy = new byte[32]; random.nextBytes(entropy);
        String secret = Base64.getUrlEncoder().withoutPadding().encodeToString(entropy);
        RegisteredClient.Builder client = RegisteredClient.withId(UUID.randomUUID().toString()).clientId(clientId)
                .clientName(request.applicationName()).clientSecret(passwords.encode(secret))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenSettings(TokenSettings.builder().accessTokenTimeToLive(Duration.ofMinutes(5)).build());
        request.scopes().forEach(client::scope);
        clients.save(client.build());
        return ResponseEntity.status(201).cacheControl(CacheControl.noStore())
                .body(new ClientReply(clientId, secret, settings.issuer() + "/oauth2/token", request.scopes()));
    }
}
