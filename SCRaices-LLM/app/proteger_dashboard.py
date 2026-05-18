"""
Protege el dashboard HTML con contraseña usando AES-GCM + PBKDF2.
Genera una versión encriptada con pantalla de login.

Uso: python proteger_dashboard.py [contraseña]
"""
import sys
import os
import json
import base64
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def encrypt_html(html_content: str, password: str) -> dict:
    """Encripta HTML con AES-256-GCM + PBKDF2"""
    salt = os.urandom(16)
    iv = os.urandom(12)

    # Derivar clave con PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = kdf.derive(password.encode('utf-8'))

    # Encriptar con AES-GCM
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, html_content.encode('utf-8'), None)

    return {
        'salt': base64.b64encode(salt).decode(),
        'iv': base64.b64encode(iv).decode(),
        'data': base64.b64encode(ciphertext).decode(),
    }


def generate_protected_html(encrypted: dict) -> str:
    """Genera HTML con login screen + decryption logic"""
    return f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Control - SG Raíces</title>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'IBM Plex Sans', sans-serif; background: #1a1a2e; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
        .login-container {{ text-align: center; max-width: 380px; width: 90%; }}
        .logo {{ width: 64px; height: 64px; background: #8B2332; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 24px; box-shadow: 0 8px 32px rgba(139,35,50,0.3); }}
        .logo span {{ color: white; font-size: 20px; font-weight: 700; font-family: 'IBM Plex Mono', monospace; }}
        h1 {{ color: #e5e7eb; font-size: 22px; font-weight: 600; margin-bottom: 6px; }}
        .subtitle {{ color: #6b7280; font-size: 13px; margin-bottom: 32px; }}
        .input-group {{ position: relative; margin-bottom: 16px; }}
        .input-group input {{
            width: 100%; padding: 14px 16px; border: 2px solid #374151; border-radius: 10px;
            background: #111827; color: #e5e7eb; font-size: 15px; font-family: 'IBM Plex Sans', sans-serif;
            outline: none; transition: border-color 0.2s;
        }}
        .input-group input:focus {{ border-color: #8B2332; }}
        .input-group input::placeholder {{ color: #4b5563; }}
        .btn {{
            width: 100%; padding: 14px; border: none; border-radius: 10px; cursor: pointer;
            font-size: 15px; font-weight: 600; font-family: 'IBM Plex Sans', sans-serif;
            background: #8B2332; color: white; transition: all 0.2s;
        }}
        .btn:hover {{ background: #a12d3f; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(139,35,50,0.4); }}
        .btn:active {{ transform: translateY(0); }}
        .btn:disabled {{ background: #374151; cursor: not-allowed; transform: none; box-shadow: none; }}
        .error {{ color: #ef4444; font-size: 13px; margin-top: 12px; display: none; }}
        .error.show {{ display: block; }}
        .loading {{ display: none; align-items: center; justify-content: center; gap: 8px; color: #9ca3af; font-size: 13px; margin-top: 12px; }}
        .loading.show {{ display: flex; }}
        .spinner {{ width: 16px; height: 16px; border: 2px solid #374151; border-top-color: #8B2332; border-radius: 50%; animation: spin 0.8s linear infinite; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .footer {{ color: #374151; font-size: 11px; margin-top: 40px; }}
    </style>
</head>
<body>
    <div class="login-container" id="loginScreen">
        <div class="logo"><span>SG</span></div>
        <h1>Panel de Control de Obras</h1>
        <p class="subtitle">SG Raíces — Acceso protegido</p>
        <form onsubmit="handleLogin(event)">
            <div class="input-group">
                <input type="password" id="passwordInput" placeholder="Contraseña" autocomplete="off" autofocus />
            </div>
            <button type="submit" class="btn" id="submitBtn">Acceder</button>
        </form>
        <p class="error" id="errorMsg">Contraseña incorrecta</p>
        <div class="loading" id="loadingMsg">
            <div class="spinner"></div>
            <span>Desencriptando dashboard...</span>
        </div>
        <p class="footer">Datos encriptados con AES-256-GCM</p>
    </div>

    <script>
        // Datos encriptados
        const ENCRYPTED = {{
            salt: "{encrypted['salt']}",
            iv: "{encrypted['iv']}",
            data: "{encrypted['data']}"
        }};

        function b64ToArray(b64) {{
            const bin = atob(b64);
            const arr = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
            return arr;
        }}

        async function decrypt(password) {{
            const salt = b64ToArray(ENCRYPTED.salt);
            const iv = b64ToArray(ENCRYPTED.iv);
            const data = b64ToArray(ENCRYPTED.data);

            // Derivar clave con PBKDF2 (mismos params que Python)
            const enc = new TextEncoder();
            const keyMaterial = await crypto.subtle.importKey(
                "raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]
            );
            const key = await crypto.subtle.deriveKey(
                {{ name: "PBKDF2", salt, iterations: 100000, hash: "SHA-256" }},
                keyMaterial,
                {{ name: "AES-GCM", length: 256 }},
                false,
                ["decrypt"]
            );

            // Desencriptar
            const decrypted = await crypto.subtle.decrypt(
                {{ name: "AES-GCM", iv }}, key, data
            );
            return new TextDecoder().decode(decrypted);
        }}

        async function handleLogin(e) {{
            e.preventDefault();
            const pwd = document.getElementById('passwordInput').value;
            if (!pwd) return;

            const btn = document.getElementById('submitBtn');
            const errEl = document.getElementById('errorMsg');
            const loadEl = document.getElementById('loadingMsg');

            btn.disabled = true;
            errEl.classList.remove('show');
            loadEl.classList.add('show');

            try {{
                const html = await decrypt(pwd);
                // Reemplazar todo el documento con el HTML desencriptado
                document.open();
                document.write(html);
                document.close();
            }} catch (err) {{
                btn.disabled = false;
                loadEl.classList.remove('show');
                errEl.classList.add('show');
                document.getElementById('passwordInput').select();
            }}
        }}

        // Enter para submit
        document.getElementById('passwordInput').addEventListener('keydown', (e) => {{
            if (e.key === 'Enter') handleLogin(e);
        }});
    </script>
</body>
</html>'''


def main():
    password = sys.argv[1] if len(sys.argv) > 1 else 'scraices2026'

    input_path = Path(__file__).parent.parent / 'dashboard' / 'index_v2.html'
    output_path = Path(__file__).parent.parent / 'dashboard' / 'index_protected.html'

    if not input_path.exists():
        print(f"ERROR: No se encontró {input_path}")
        sys.exit(1)

    print(f"Leyendo dashboard: {input_path} ({input_path.stat().st_size / 1024:.0f} KB)")

    with open(input_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    print(f"Encriptando con AES-256-GCM (PBKDF2 100k iteraciones)...")
    encrypted = encrypt_html(html_content, password)

    print(f"Generando HTML protegido...")
    protected_html = generate_protected_html(encrypted)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(protected_html)

    print(f"\nDashboard protegido: {output_path}")
    print(f"  Tamaño: {output_path.stat().st_size / 1024:.0f} KB")
    print(f"  Contraseña: {'*' * len(password)}")
    return str(output_path)


if __name__ == '__main__':
    main()
