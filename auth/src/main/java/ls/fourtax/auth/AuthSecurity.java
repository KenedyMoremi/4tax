package ls.fourtax.auth;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.server.authorization.client.*;
import org.springframework.security.config.annotation.web.configurers.oauth2.server.authorization.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.*;
import org.springframework.security.oauth2.server.authorization.token.*;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableConfigurationProperties(AuthSettings.class)
public class AuthSecurity {
    @Bean PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(12); }

    @Bean RSAKey signingKey(AuthSettings settings) throws Exception {
        if (settings.signingJwk() != null && !settings.signingJwk().isBlank()) {
            RSAKey key;
            try { key = RSAKey.parse(settings.signingJwk()); }
            catch (Exception error) { throw new IllegalArgumentException("Invalid configured auth signing key"); }
            if (!key.isPrivate() || key.size() < 2048 || key.getKeyID() == null || key.getKeyID().isBlank())
                throw new IllegalArgumentException("Configure a private RSA signing key with a stable key ID and at least 2048 bits");
            return key;
        }
        KeyStore store = KeyStore.getInstance("PKCS12");
        char[] password = settings.keyStorePassword().toCharArray();
        try (InputStream input = Files.newInputStream(Path.of(settings.keyStore()))) { store.load(input, password); }
        String alias = settings.keyAlias();
        return new RSAKey.Builder((RSAPublicKey) store.getCertificate(alias).getPublicKey())
                .privateKey((RSAPrivateKey) store.getKey(alias, password)).keyID(alias).build();
    }

    @Bean JWKSource<SecurityContext> jwkSource(RSAKey key) {
        JWKSet keys = new JWKSet(key);
        return (selector, context) -> selector.select(keys);
    }

    @Bean JwtEncoder jwtEncoder(JWKSource<SecurityContext> keys) { return new NimbusJwtEncoder(keys); }

    @Bean JwtDecoder jwtDecoder(RSAKey key, AuthSettings settings) throws Exception {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withPublicKey(key.toRSAPublicKey()).build();
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(settings.issuer()), new JwtTimestampValidator(Duration.ZERO), jwt ->
                jwt.getAudience().contains("auth-api") && "application".equals(jwt.getClaimAsString("kind"))
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token"))));
        return decoder;
    }

    @Bean RegisteredClientRepository registeredClients(JdbcTemplate jdbc) {
        return new JdbcRegisteredClientRepository(jdbc);
    }

    @Bean AuthorizationServerSettings authorizationSettings(AuthSettings settings) {
        return AuthorizationServerSettings.builder().issuer(settings.issuer()).build();
    }

    @Bean OAuth2TokenCustomizer<JwtEncodingContext> applicationClaims() {
        return context -> context.getClaims().audience(List.of("auth-api")).claim("kind", "application");
    }

    @Bean @Order(1) SecurityFilterChain authorizationChain(HttpSecurity http) throws Exception {
        var authorization = new OAuth2AuthorizationServerConfigurer();
        http.securityMatcher(authorization.getEndpointsMatcher())
                .with(authorization, Customizer.withDefaults())
                .authorizeHttpRequests(requests -> requests.anyRequest().authenticated());
        return http.build();
    }

    @Bean @Order(2) SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http.csrf(csrf -> csrf.disable()).sessionManagement(session -> session
                .sessionCreationPolicy(org.springframework.security.config.http.SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/api/v1/clients").permitAll()
                        .requestMatchers("/api/v1/auth/owners/lookup").hasAuthority("SCOPE_owners:login")
                        .requestMatchers("/api/v1/auth/owners").hasAuthority("SCOPE_owners:create")
                        .requestMatchers("/api/v1/auth/pin/login").hasAuthority("SCOPE_owners:login")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resource -> resource.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
