"use strict";

/* Where the AIMS API lives.
 *
 * "" (default) means same-origin: the FastAPI app is serving this file
 * itself, so /api/... resolves against the page's own host. This is the
 * right setting whenever app.py serves static/ directly (local dev, or a
 * single deployment on Render/Railway/etc).
 *
 * The GitHub Pages workflow replaces this file only inside the deployment
 * artifact, using the public AIMS_API_BASE repository variable. The committed
 * file therefore remains correct for local same-origin development and never
 * contains a secret.
 */
window.AIMS_API_BASE = "";
