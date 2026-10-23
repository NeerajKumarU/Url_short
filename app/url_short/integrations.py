from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    available: bool
    detail: str


class DnsVerificationProvider:
    """Abstraction point for a real TXT resolver/provider integration."""

    def verify_txt(self, domain):
        return VerificationResult(
            verified=False,
            available=False,
            detail=(
                "Automated DNS verification is not configured. Keep the domain pending "
                "until an administrator verifies the TXT record with an approved resolver."
            ),
        )


dns_verification_provider = DnsVerificationProvider()
