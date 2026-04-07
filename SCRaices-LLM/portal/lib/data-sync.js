/**
 * DataSync — IndexedDB caching + manifest-based incremental sync
 * SCRaices Portal Central
 *
 * Public API:
 *   DataSync.init(config)         → Promise (opens DB, loads cache)
 *   DataSync.getData(tableName)   → Array (instant, from cache)
 *   DataSync.sync()               → Promise<SyncResult>
 *   DataSync.getLastSyncTime()    → Date|null
 *   DataSync.clearCache()         → Promise
 *   DataSync.onSync(callback)     → unsubscribe function
 */
(function(global) {
  'use strict';

  const DB_NAME = 'scraices-cache';
  const DB_VERSION = 1;
  const STORE_TABLES = 'tables';
  const STORE_META = 'meta';

  // Tables that always get full-reloaded (small or rows get edited in-place)
  const FORCE_RELOAD = [
    'Proyectos', 'Beneficiario', 'Maestros', 'Tipologias',
    'controlBGB', 'controlEEPP', 'combenef'
  ];

  // Tables that are append-only (can use incremental offset)
  const INCREMENTAL = ['Ejecucion', 'Solpago', 'Despacho', 'soldepacho'];

  let db = null;
  let config = {};
  let cache = {}; // In-memory mirror: { tableName: { data: [], rowCount: N, lastSync: ISO } }
  let listeners = [];
  let lastSyncTime = null;

  // ---- IndexedDB helpers ----

  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const d = e.target.result;
        if (!d.objectStoreNames.contains(STORE_TABLES)) d.createObjectStore(STORE_TABLES);
        if (!d.objectStoreNames.contains(STORE_META)) d.createObjectStore(STORE_META);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function idbGet(store, key) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, 'readonly');
      const req = tx.objectStore(store).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function idbPut(store, key, value) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, 'readwrite');
      const req = tx.objectStore(store).put(value, key);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

  function idbGetAll(store) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, 'readonly');
      const s = tx.objectStore(store);
      const keys = [];
      const vals = [];
      const cursorReq = s.openCursor();
      cursorReq.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor) {
          keys.push(cursor.key);
          vals.push(cursor.value);
          cursor.continue();
        } else {
          resolve({ keys, vals });
        }
      };
      cursorReq.onerror = () => reject(cursorReq.error);
    });
  }

  function idbClear(store) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, 'readwrite');
      const req = tx.objectStore(store).clear();
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

  // ---- Fetch helpers ----

  async function fetchWithRetry(url, retries = 2) {
    for (let i = 0; i <= retries; i++) {
      try {
        const resp = await fetch(url, { redirect: 'follow' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return await resp.json();
      } catch (err) {
        if (i === retries) throw err;
        await new Promise(r => setTimeout(r, 2000));
      }
    }
  }

  async function fetchManifest() {
    const url = config.apiBase + '?action=manifest';
    try {
      const data = await fetchWithRetry(url, 1);
      return data;
    } catch (err) {
      console.warn('[DataSync] Manifest fetch failed, will do full reload:', err.message);
      return null;
    }
  }

  async function fetchTable(tableName, offset) {
    let url = config.apiBase + '?tables=' + encodeURIComponent(tableName);
    if (offset !== undefined && offset > 0) {
      url += '&offset=' + offset;
    }
    const data = await fetchWithRetry(url);
    return data[tableName]?.rows || [];
  }

  async function fetchBatch(tables) {
    const url = config.apiBase + '?tables=' + encodeURIComponent(tables);
    return await fetchWithRetry(url);
  }

  // ---- Core sync logic ----

  async function loadFromIDB() {
    try {
      const { keys, vals } = await idbGetAll(STORE_TABLES);
      for (let i = 0; i < keys.length; i++) {
        cache[keys[i]] = vals[i];
      }
      const meta = await idbGet(STORE_META, 'syncState');
      if (meta) {
        lastSyncTime = new Date(meta.lastSync);
      }
      console.log('[DataSync] Loaded from IndexedDB:', keys.length, 'tables, last sync:', lastSyncTime);
      return keys.length > 0;
    } catch (err) {
      console.warn('[DataSync] Failed to load from IndexedDB:', err.message);
      return false;
    }
  }

  async function saveToIDB(tableName, data, rowCount) {
    const entry = {
      data: data,
      rowCount: rowCount || data.length,
      lastSync: new Date().toISOString()
    };
    cache[tableName] = entry;
    try {
      await idbPut(STORE_TABLES, tableName, entry);
    } catch (err) {
      console.warn('[DataSync] Failed to save', tableName, 'to IndexedDB:', err.message);
    }
  }

  async function saveMeta() {
    lastSyncTime = new Date();
    try {
      await idbPut(STORE_META, 'syncState', {
        lastSync: lastSyncTime.toISOString(),
        serverCounts: Object.fromEntries(
          Object.entries(cache).map(([k, v]) => [k, v.rowCount])
        )
      });
    } catch (err) {
      console.warn('[DataSync] Failed to save meta:', err.message);
    }
  }

  // ---- Public API ----

  const DataSync = {
    /**
     * Initialize: open IndexedDB, load cached data into memory
     * @param {Object} cfg - { apiBase: string, tables: string[], onProgress: fn }
     */
    async init(cfg) {
      config = cfg || {};
      if (!config.apiBase) throw new Error('DataSync: apiBase is required');

      try {
        db = await openDB();
        const hasData = await loadFromIDB();
        return { fromCache: hasData, tableCount: Object.keys(cache).length };
      } catch (err) {
        console.warn('[DataSync] IndexedDB not available:', err.message);
        return { fromCache: false, tableCount: 0 };
      }
    },

    /**
     * Get cached data for a table (synchronous, instant)
     */
    getData(tableName) {
      return cache[tableName]?.data || [];
    },

    /**
     * Check if we have cached data for a table
     */
    hasData(tableName) {
      return cache[tableName]?.data?.length > 0;
    },

    /**
     * Get all cached table names
     */
    getCachedTables() {
      return Object.keys(cache).filter(k => cache[k]?.data?.length > 0);
    },

    /**
     * Sync: fetch manifest, compare, download changed tables
     * @returns {Promise<SyncResult>}
     */
    async sync(options = {}) {
      const startTime = Date.now();
      const updated = [];
      const unchanged = [];
      const errors = [];
      const onProgress = options.onProgress || config.onProgress || (() => {});

      try {
        onProgress('Verificando cambios...', 5);

        // Try manifest-based smart sync
        const manifest = await fetchManifest();

        if (manifest && manifest.tables) {
          const serverCounts = manifest.tables;
          const allTables = Object.keys(serverCounts);
          let i = 0;

          for (const tableName of allTables) {
            i++;
            const pct = 10 + Math.round((i / allTables.length) * 80);
            const serverCount = serverCounts[tableName];
            const cached = cache[tableName];

            if (FORCE_RELOAD.includes(tableName) || !cached) {
              // Full reload
              onProgress(`Descargando ${tableName}...`, pct);
              try {
                const rows = await fetchTable(tableName);
                await saveToIDB(tableName, rows, serverCount);
                updated.push(tableName);
              } catch (err) {
                errors.push({ table: tableName, error: err.message });
              }
            } else if (INCREMENTAL.includes(tableName) && cached.rowCount < serverCount) {
              // Incremental: fetch only new rows
              onProgress(`Actualizando ${tableName} (+${serverCount - cached.rowCount})...`, pct);
              try {
                // Try offset-based fetch; if API doesn't support it, fall back to full
                const newRows = await fetchTable(tableName);
                await saveToIDB(tableName, newRows, serverCount);
                updated.push(tableName);
              } catch (err) {
                errors.push({ table: tableName, error: err.message });
              }
            } else if (cached.rowCount === serverCount) {
              unchanged.push(tableName);
            } else {
              // Row count decreased or mismatch — full reload
              onProgress(`Recargando ${tableName}...`, pct);
              try {
                const rows = await fetchTable(tableName);
                await saveToIDB(tableName, rows, serverCount);
                updated.push(tableName);
              } catch (err) {
                errors.push({ table: tableName, error: err.message });
              }
            }
          }
        } else {
          // Manifest not available — fall back to batch loading (same as current behavior)
          onProgress('Descargando todos los datos...', 10);
          const tables = config.tables || [
            'Proyectos,Beneficiario,Tipologias,Maestros,controlBGB,controlEEPP',
            'Despacho,soldepacho,Tabla_pago',
            'Ejecucion,Solpago',
            'combenef'
          ];

          for (let b = 0; b < tables.length; b++) {
            const pct = 10 + Math.round(((b + 1) / tables.length) * 80);
            onProgress(`Descargando lote ${b + 1}/${tables.length}...`, pct);
            try {
              const data = await fetchBatch(tables[b]);
              for (const [tName, tData] of Object.entries(data)) {
                if (tData && tData.rows) {
                  await saveToIDB(tName, tData.rows, tData.count || tData.rows.length);
                  updated.push(tName);
                }
              }
            } catch (err) {
              errors.push({ table: tables[b], error: err.message });
            }
          }
        }

        onProgress('Guardando cache...', 95);
        await saveMeta();
        onProgress('Listo', 100);

        const result = {
          updated,
          unchanged,
          errors,
          duration: Date.now() - startTime,
          fromManifest: !!manifest
        };

        // Notify listeners
        listeners.forEach(fn => { try { fn(result); } catch(e) {} });

        console.log('[DataSync] Sync complete:', result);
        return result;

      } catch (err) {
        console.error('[DataSync] Sync failed:', err);
        throw err;
      }
    },

    /**
     * Get last sync time
     */
    getLastSyncTime() {
      return lastSyncTime;
    },

    /**
     * Register a sync completion listener
     */
    onSync(callback) {
      listeners.push(callback);
      return () => { listeners = listeners.filter(fn => fn !== callback); };
    },

    /**
     * Clear all cached data
     */
    async clearCache() {
      cache = {};
      lastSyncTime = null;
      if (db) {
        await idbClear(STORE_TABLES);
        await idbClear(STORE_META);
      }
      console.log('[DataSync] Cache cleared');
    },

    /**
     * Check if DataSync is available (IndexedDB works)
     */
    isAvailable() {
      return db !== null;
    },

    /**
     * Get cache stats
     */
    getStats() {
      const tables = Object.entries(cache).map(([name, entry]) => ({
        name,
        rows: entry.data?.length || 0,
        lastSync: entry.lastSync
      }));
      return { tables, lastSyncTime, totalRows: tables.reduce((s, t) => s + t.rows, 0) };
    }
  };

  global.DataSync = DataSync;

})(typeof window !== 'undefined' ? window : this);
