# Security Policy

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of the Journal Assessment Tool seriously. If you discover a security vulnerability, please follow these guidelines:

### How to Report

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. Send an email to [Andreas.Florath@telekom.de] with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Any suggested fixes (optional)

### What to Include

- **Vulnerability Type**: Authentication, authorization, data exposure, etc.
- **Affected Components**: Which part of the system is affected
- **Attack Vector**: How the vulnerability could be exploited
- **Impact Assessment**: Potential consequences if exploited
- **Reproducibility**: Step-by-step instructions to reproduce
- **Environment Details**: OS, Python version, package versions

### Response Timeline

- **Initial Response**: Within 4 business of report
- **Assessment**: Within 10 business days
- **Fix Development**: Depends on complexity, but typically within 4 weeks
- **Public Disclosure**: After fix is released and users have had time to update

## Security Considerations

### Data Handling

This tool handles academic journal data which may include:
- Journal names and metadata
- ISSN numbers
- Publisher information
- Assessment results

**Privacy Measures:**
- No personal data is collected or stored
- Journal queries are cached locally only
- No data is transmitted to third parties except documented API calls
- Users can clear local cache at any time

### API Security

**External API Calls:**
- DOAJ API: Public data, rate-limited
- Retraction Watch: Public data via GitLab
- OpenAlex API: Public academic data

**Security Practices:**
- All API calls use HTTPS
- Rate limiting to prevent abuse
- Timeout handling to prevent hanging requests
- Input validation to prevent injection attacks
- Following the API guidelines (e.g. OpenAlex, Crossref), you might choose that your email address is used in API calls

### Local Security

**Cache Storage:**
- Local files stored in user's home or the current project directory
- Standard file permissions (user read/write only)
- No sensitive authentication data stored
- Cache can be cleared via CLI command

**Configuration:**
- YAML configuration files with standard permissions
- No passwords or secrets in configuration
- Optional email addresses to follow API guidelines of external services
- Environment variable support for sensitive settings

### Common Vulnerabilities

**Input Validation:**
- All journal names are sanitized before processing
- ISSN format validation
- Protection against code injection via journal names

**Dependency Security:**
- Regular dependency updates
- Vulnerability scanning of dependencies
- Minimal dependency tree to reduce attack surface

**Network Security:**
- HTTPS-only for all external communications
- Certificate verification enabled
- Timeout settings to prevent resource exhaustion

## Security Best Practices for Users

### Installation
```bash
# Always install from official sources
pip install aletheia-probe

# Verify package integrity (when available)
pip install --trusted-host pypi.org aletheia-probe
```

### Configuration
- Store configuration files with appropriate permissions (600)
- Use environment variables for any sensitive settings
- Regularly review and update backend configurations

### Usage
- Don't run with elevated privileges unless necessary
- Keep the tool updated to latest version
- Report any suspicious behavior or unexpected network traffic

### Development
- Use virtual environments
- Keep development dependencies updated
- Run security linters (bandit) on code changes
- Review all external dependencies

## Threat Model

### In Scope
- Input validation vulnerabilities
- Dependency vulnerabilities
- Local file access issues
- Network request vulnerabilities
- Configuration security issues

### Out of Scope
- Issues in third-party APIs we query
- General system security (OS, network infrastructure)
- Physical access to systems running the tool
- Social engineering attacks

## Security Updates

When security issues are discovered:

1. **Assessment**: Evaluate severity and impact
2. **Fix Development**: Develop and test fix
3. **Security Advisory**: Prepare advisory for users
4. **Release**: Release patched version
5. **Notification**: Notify users via GitHub releases and PyPI

### Severity Classification

- **Critical**: Immediate action required, major data exposure risk
- **High**: Significant security risk, patch within days
- **Medium**: Moderate risk, patch within weeks
- **Low**: Minor risk, can be addressed in regular updates

## Acknowledgments

We appreciate security researchers who responsibly disclose vulnerabilities. Contributors will be acknowledged in:
- Security advisories
- Release notes
- Project documentation

Thank you for helping keep the Aletheia Probe secure for the academic community.

---

**Note**: This security policy applies to the Aletheia Probe software itself. For security issues related to the data sources we query (DOAJ, Retraction Watch, etc.), please contact those organizations directly.
