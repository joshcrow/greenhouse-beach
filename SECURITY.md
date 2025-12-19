# 🔐 Security Guidelines

**Mandatory reading for all Project Chlorophyll development.**

---

## 🚨 Golden Rules

1. **NEVER commit secrets** - All credentials go in `.env` or gitignored files
2. **Use placeholders** - Example files use `YOUR_*` or `CHANGE_ME` patterns
3. **Verify before push** - Run `git diff --staged | grep -iE "password|key|secret"`
4. **Rotate exposed secrets** - If leaked, change immediately

---

## 📁 File Classification

### ⛔ NEVER Commit (Must be in .gitignore)
```
.env                          # API keys, SMTP, DB passwords
esphome/secrets.yaml          # WiFi, MQTT credentials  
esphome/sensors/*.yaml        # Device configs with real passwords
configs/passwd                # MQTT password hashes
*.pem, *.key, *.crt          # TLS certificates
```

### ✅ Safe to Commit
```
.env.example                  # Template with placeholders
esphome/secrets.example.yaml  # Template with placeholders
esphome/sensors/*.example.yaml
configs/passwd.example        # Instructions only
```

---

## 🔒 MQTT Security

### Current Risks
- **No TLS**: Traffic is plaintext (readable on network)
- **No ACLs**: All users can access all topics
- **Weak password**: Default is easily guessable

### Minimum Security (Current)
```conf
allow_anonymous false
password_file /mosquitto/config/passwd
```

### Recommended Security (Production)
```conf
# TLS encryption
listener 8883 0.0.0.0
cafile /mosquitto/config/ca.crt
certfile /mosquitto/config/server.crt
keyfile /mosquitto/config/server.key

# Require client certificates (mutual TLS)
require_certificate true

# Access control lists
acl_file /mosquitto/config/acl.conf
```

### Strong Password Setup
```bash
# Generate a strong password
openssl rand -base64 24
# Example output: <GENERATED_PASSWORD>

# Set it in Mosquitto
docker exec -it greenhouse-beach-mosquitto-1 \
  mosquitto_passwd -c /mosquitto/config/passwd greenhouse

# Update .env to match
MQTT_PASSWORD=<GENERATED_PASSWORD>

# Update ESPHome configs to match
# esphome/secrets.yaml: mqtt_password: "<GENERATED_PASSWORD>"
```

---

## 🔑 API Key Management

### Environment Variables (Preferred)
```python
# ✅ GOOD - Read from environment
api_key = os.getenv("GEMINI_API_KEY")

# ⛔ BAD - Hardcoded
api_key = "AIzaSy..."
```

### Key Rotation Schedule
| Service | Rotation Frequency | How to Rotate |
|---------|-------------------|---------------|
| Gemini API | On exposure | Google Cloud Console |
| OpenWeather | On exposure | OpenWeather Dashboard |
| Gmail App Password | On exposure | Google Account Security |
| MQTT Password | Quarterly | mosquitto_passwd command |
| WiFi Passwords | On exposure | Router admin panel |

---

## 🛡️ Pre-Commit Checklist

Before every `git push`:

```bash
# 1. Check for secrets in staged files
git diff --staged | grep -iE "password|passwd|secret|api_key|token|key.*=" 

# 2. Verify .gitignore is working
git status | grep -E "\.env|secrets\.yaml"
# Should show NOTHING (files are ignored)

# 3. Check for hardcoded IPs that might reveal infrastructure
git diff --staged | grep -E "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"
```

### Automated Pre-Commit Hook (Optional)
```bash
# Create .git/hooks/pre-commit
cat << 'EOF' > .git/hooks/pre-commit
#!/bin/bash
# Block commits containing secrets

PATTERNS="password.*=|api_key.*=|secret.*=|AIzaSy|ghp_|sk-"

if git diff --cached | grep -iE "$PATTERNS" | grep -v "YOUR_\|CHANGE\|example\|placeholder"; then
    echo "⛔ BLOCKED: Potential secret detected in commit!"
    echo "Review with: git diff --cached"
    exit 1
fi
EOF
chmod +x .git/hooks/pre-commit
```

---

## 🌐 Network Security

### Current Architecture
```
Internet
    │
BeachFi Router (192.168.1.1)
    │
    ├── Storyteller Pi (192.168.1.50)
    │   └── MQTT :1883 (unencrypted) ⚠️
    │
    └── Greenhouse Pi (192.168.1.X)
        └── GREENHOUSE_IOT AP (10.0.0.0/24)
            └── Satellites
```

### Risks
- Anyone on BeachFi can sniff MQTT traffic
- MQTT password transmitted in plaintext
- Sensor data visible to network observers

### Mitigations
1. **TLS for MQTT** (best but complex)
2. **VPN/Tailscale only** (current - good)
3. **Firewall rules** (limit MQTT to specific IPs)

---

## 📋 Security Incident Response

### If Credentials Are Exposed

1. **Immediate**: Rotate the credential
2. **Assess**: Check git history with `git log -p -S "leaked_value"`
3. **Scrub**: Use `git filter-branch` to remove from history
4. **Force push**: `git push --force`
5. **Notify**: If public repo, assume compromised

### Current Credentials Status

| Credential | Status | Action Needed |
|------------|--------|---------------|
| WiFi passwords | 🟢 Scrubbed | Rotate anyway (were exposed) |
| MQTT password | 🟡 Weak | Generate strong password |
| API keys | 🟢 In .env | Verify not in history |
| ESPHome API key | 🟢 Gitignored | None |

---

## 🔄 Adding New Services

When adding new integrations:

1. **Create environment variable** in `.env.example` with placeholder
2. **Never hardcode** credentials in Python/YAML
3. **Document** in this file under "Key Rotation Schedule"
4. **Test** with `grep -r "actual_password" .` before committing

---

## 📊 Security Audit Commands

```bash
# Full credential scan
grep -rn --include="*.py" --include="*.yaml" --include="*.md" \
  -iE "(password|secret|key|token)\s*[:=]" . | grep -v ".git"

# Check what's tracked vs ignored
git ls-files | xargs grep -l -iE "password|api_key" 2>/dev/null

# Verify .gitignore effectiveness  
git status --ignored | grep -E "\.env|secrets"

# Search git history for leaks
git log -p --all | grep -iE "AIzaSy|password.*=" | head -20
```

---

*Last Updated: December 19, 2025*
