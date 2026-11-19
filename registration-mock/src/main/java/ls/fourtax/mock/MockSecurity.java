package ls.fourtax.mock;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MockSecurity {
    @Bean JwtDecoder decoder(@Value("${mock.issuer}") String issuer, @Value("${mock.jwks-url}") String jwks) {
        var decoder = NimbusJwtDecoder.withJwkSetUri(jwks).build();
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(issuer), new JwtTimestampValidator(java.time.Duration.ZERO), jwt ->
                jwt.getAudience().contains("registration-api") && "owner".equals(jwt.getClaimAsString("kind"))
                        ? OAuth2TokenValidatorResult.success() : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token"))));
        return decoder;
    }
    @Bean SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http.csrf(csrf -> csrf.disable()).sessionManagement(session -> session
                        .sessionCreationPolicy(org.springframework.security.config.http.SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(request -> request.requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/api/v1/businesses").hasAuthority("SCOPE_businesses:create").anyRequest().denyAll())
                .oauth2ResourceServer(resource -> resource.jwt(Customizer.withDefaults())).build();
    }
}
