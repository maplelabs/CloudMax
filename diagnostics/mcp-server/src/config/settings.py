"""Configuration settings for the MCP server."""
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Kafka Configuration
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: Optional[str] = None
    kafka_sasl_username: Optional[str] = None
    kafka_sasl_password: Optional[str] = None

    # Lag Thresholds
    lag_threshold_warning: int = 1000
    lag_threshold_critical: int = 5000

    # DLQ Configuration
    dlq_topic_suffix: str = "-dlq"
    dlq_sample_size: int = 10

    # Server Configuration
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    log_level: str = "INFO"

    # PostgreSQL Configuration
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_database: str = "hotel_booking_db"
    postgres_user: str = "postgres"
    postgres_password: str = "password"
    postgres_timeout: int = 10  # Connection timeout in seconds

    # SSL/TLS Configuration (mTLS)
    use_ssl: bool = False
    ssl_cert_file: Optional[str] = "certs/server-cert.pem"
    ssl_key_file: Optional[str] = "certs/server-key.pem"
    ssl_ca_file: Optional[str] = "certs/ca-cert.pem"
    ssl_client_cert_file: Optional[str] = "certs/client-cert.pem"
    ssl_client_key_file: Optional[str] = "certs/client-key.pem"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def get_kafka_config(self) -> dict:
        """Get Kafka client configuration."""
        config = {
            "bootstrap.servers": self.kafka_bootstrap_servers,
            "security.protocol": self.kafka_security_protocol,
            # Set reasonable timeouts to avoid hanging
            "socket.timeout.ms": 10000,  # 10 seconds
            "connections.max.idle.ms": 30000,  # 30 seconds
            "request.timeout.ms": 10000,  # 10 seconds
        }

        if self.kafka_sasl_mechanism:
            config["sasl.mechanism"] = self.kafka_sasl_mechanism
        if self.kafka_sasl_username:
            config["sasl.username"] = self.kafka_sasl_username
        if self.kafka_sasl_password:
            config["sasl.password"] = self.kafka_sasl_password

        return config

    def get_postgres_connection_params(self) -> dict:
        """Get PostgreSQL connection parameters."""
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "database": self.postgres_database,
            "user": self.postgres_user,
            "password": self.postgres_password,
            "connect_timeout": self.postgres_timeout,
        }

    def get_ssl_context(self):
        """Get SSL context for mTLS connections."""
        import ssl
    
        if not self.use_ssl:
            return None

        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.load_cert_chain(
            certfile=self.ssl_cert_file,
            keyfile=self.ssl_key_file,
            password=None
        )
        context.load_verify_locations(self.ssl_ca_file)
        context.verify_mode = ssl.CERT_REQUIRED

        return context

    def get_client_ssl_context(self):
        """Get SSL context for client connections with mTLS."""
        import ssl

        if not self.use_ssl:
            return None

        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.load_cert_chain(
            certfile=self.ssl_client_cert_file,
            keyfile=self.ssl_client_key_file,
            password=None
        )
        context.load_verify_locations(self.ssl_ca_file)
        context.verify_mode = ssl.CERT_REQUIRED

        return context


# Global settings instance
settings = Settings()

