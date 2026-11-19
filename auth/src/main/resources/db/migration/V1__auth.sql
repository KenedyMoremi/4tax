create table owner_credentials (
    id uuid primary key,
    mobile_number varchar(16) not null unique,
    pin_hash varchar(100) not null,
    creation_key varchar(128) not null unique,
    failed_attempts integer not null default 0,
    locked_until timestamptz,
    created_at timestamptz not null default current_timestamp
);

create table oauth2_registered_client (
    id varchar(100) primary key,
    client_id varchar(100) not null unique,
    client_id_issued_at timestamp not null default current_timestamp,
    client_secret varchar(200),
    client_secret_expires_at timestamp,
    client_name varchar(200) not null,
    client_authentication_methods varchar(1000) not null,
    authorization_grant_types varchar(1000) not null,
    redirect_uris varchar(1000),
    post_logout_redirect_uris varchar(1000),
    scopes varchar(1000) not null,
    client_settings varchar(2000) not null,
    token_settings varchar(2000) not null
);
