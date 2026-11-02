# HTTPS Setup for Camera/Barcode Scanner

The barcode scanner requires HTTPS (or localhost) to access the device camera. Here are your options:

## Option 1: ngrok (Easiest for Quick Testing)

**Best for:** Testing on your phone without certificate warnings

```bash
# Install ngrok from https://ngrok.com/download
# Then run:
ngrok http 5000
```

Access the HTTPS URL from your phone (e.g., `https://abc123.ngrok-free.app`)

**Pros:** No certificate warnings, works immediately
**Cons:** Requires internet, URL changes each restart (unless paid plan)

---

## Option 2: Self-Signed Certificate (Local Network)

**Best for:** Local development on your network

### Step 1: Generate Certificate

```bash
./generate-cert.sh
```

This creates:
- `certs/cert.pem` (certificate)
- `certs/key.pem` (private key)

### Step 2: Run with HTTPS

```bash
python3 app.py --cert certs/cert.pem --key certs/key.pem
```

### Step 3: Access from Phone

1. Find your computer's IP: `ip addr` or `ifconfig`
2. Access `https://192.168.x.x:5000` from phone
3. **Accept certificate warning** (this is safe - it's your own certificate)
   - Chrome: Click "Advanced" → "Proceed to 192.168.x.x (unsafe)"
   - Safari: Click "Show Details" → "visit this website"

**Pros:** Works on local network, no external service needed
**Cons:** Browser warning (must click through), certificate expires in 365 days

---

## Option 3: Docker with HTTPS

### Step 1: Generate certificate (same as above)

```bash
./generate-cert.sh
```

### Step 2: Update docker-compose.yml

Add the certs volume:

```yaml
volumes:
  - ./static/uploads:/app/static/uploads
  - ./instance:/app/instance
  - ./certs:/app/certs  # Add this line
```

### Step 3: Update Dockerfile CMD

Replace the last line with:

```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", \
     "--certfile=/app/certs/cert.pem", "--keyfile=/app/certs/key.pem", \
     "app:create_app()"]
```

### Step 4: Rebuild and run

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## Option 4: Production Setup (Real Certificate)

**Best for:** Actual production deployment

Use a reverse proxy (nginx/traefik) with Let's Encrypt:

1. Get a domain name
2. Point it to your server
3. Use Certbot to get free SSL certificate
4. Configure nginx to proxy to your Flask app

(This is more complex but gives you a real, trusted certificate)

---

## Quick Comparison

| Method | Setup Time | Certificate Warning | Works Offline | Best For |
|--------|------------|-------------------|---------------|----------|
| ngrok | 2 min | ❌ No | ❌ No | Quick testing |
| Self-signed | 5 min | ⚠️ Yes (once) | ✅ Yes | Local development |
| Docker + self-signed | 10 min | ⚠️ Yes (once) | ✅ Yes | Local production |
| Real certificate | 30+ min | ❌ No | ✅ Yes | Real production |

---

## Troubleshooting

**"Your connection is not private" warning**
- This is normal with self-signed certificates
- Click "Advanced" → "Proceed anyway"
- You only need to do this once per device

**Still getting getUserMedia error**
- Make sure you're using `https://` not `http://`
- Check that the certificate files exist in `certs/`
- Try clearing browser cache and reloading

**Can't access from phone**
- Make sure phone is on same WiFi network
- Check firewall isn't blocking port 5000
- Try accessing from computer first to verify it works

---

## Recommended Approach

For your use case, I recommend:

1. **Development:** Use ngrok for initial testing
2. **Local server:** Use self-signed certificate
3. **Production:** Set up nginx + Let's Encrypt

The self-signed approach is included and ready to go - just run `./generate-cert.sh` and restart with the SSL flags!
