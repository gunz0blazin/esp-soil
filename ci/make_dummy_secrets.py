"""Write throwaway secrets so CI can validate and compile firmware.
Nothing real is ever used in CI; the values are random per run."""
import base64, os, secrets, sys
vals = {
    "wifi_ssid": "ci-network",
    "wifi_password": secrets.token_urlsafe(12),
    "web_username": "esp",
    "web_password": secrets.token_urlsafe(12),
    "ota_password": secrets.token_urlsafe(12),
    "api_key": base64.b64encode(os.urandom(32)).decode(),
    "fallback_password": secrets.token_urlsafe(12),
}
for path in sys.argv[1:]:
    with open(path, "w") as f:
        f.writelines(f'{k}: "{v}"\n' for k, v in vals.items())
    print("wrote", path)
