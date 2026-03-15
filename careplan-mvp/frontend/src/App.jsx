import { useState, useEffect, useRef } from 'react'

// ===========================================================================
// 样式定义
// ===========================================================================
const styles = {
  page: {
    minHeight: '100vh',
    background: '#f0f2f5',
    padding: '30px 20px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  container: {
    maxWidth: '1100px',
    margin: '0 auto',
  },
  header: {
    textAlign: 'center',
    marginBottom: '8px',
    color: '#1a1a2e',
    fontSize: '28px',
    fontWeight: '700',
  },
  subtitle: {
    textAlign: 'center',
    color: '#666',
    marginBottom: '32px',
    fontSize: '15px',
  },
  card: {
    background: 'white',
    borderRadius: '10px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
    padding: '32px',
    marginBottom: '20px',
  },
  cardTitle: {
    fontSize: '18px',
    fontWeight: '600',
    color: '#333',
    marginBottom: '20px',
  },
  // Drop zone
  dropzone: {
    border: '2px dashed #c8d0e0',
    borderRadius: '8px',
    padding: '48px 24px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    marginBottom: '20px',
    background: '#fafbfd',
  },
  dropzoneActive: {
    border: '2px dashed #0066cc',
    background: '#e8f0fd',
  },
  dropzoneHasFile: {
    border: '2px solid #28a745',
    background: '#f0fff4',
  },
  dropzoneIcon: {
    fontSize: '48px',
    marginBottom: '12px',
  },
  dropzoneText: {
    fontSize: '16px',
    color: '#444',
    marginBottom: '6px',
    fontWeight: '500',
  },
  dropzoneHint: {
    fontSize: '13px',
    color: '#888',
  },
  // Buttons
  button: {
    background: '#0066cc',
    color: 'white',
    border: 'none',
    padding: '13px 32px',
    borderRadius: '6px',
    fontSize: '15px',
    fontWeight: '600',
    cursor: 'pointer',
    width: '100%',
    transition: 'background 0.2s',
  },
  buttonDisabled: {
    background: '#b0bec5',
    cursor: 'not-allowed',
  },
  downloadButton: {
    background: '#28a745',
    color: 'white',
    border: 'none',
    padding: '11px 24px',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    flex: 1,
    transition: 'background 0.2s',
  },
  resetButton: {
    background: '#6c757d',
    color: 'white',
    border: 'none',
    padding: '11px 24px',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    flex: 1,
    transition: 'background 0.2s',
  },
  buttonRow: {
    display: 'flex',
    gap: '12px',
    marginTop: '20px',
  },
  // Status banners
  statusBanner: {
    padding: '16px 20px',
    borderRadius: '6px',
    marginBottom: '20px',
    textAlign: 'center',
  },
  status_pending: {
    background: '#fff3cd',
    color: '#856404',
    border: '1px solid #ffc107',
  },
  status_processing: {
    background: '#cce5ff',
    color: '#004085',
    border: '1px solid #b8daff',
  },
  status_completed: {
    background: '#d4edda',
    color: '#155724',
    border: '1px solid #c3e6cb',
  },
  status_failed: {
    background: '#f8d7da',
    color: '#721c24',
    border: '1px solid #f5c6cb',
  },
  // Request info bar
  requestInfo: {
    display: 'flex',
    gap: '24px',
    padding: '12px 16px',
    background: '#f8f9fa',
    borderRadius: '6px',
    marginBottom: '20px',
    fontSize: '13px',
    color: '#555',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  requestId: {
    fontFamily: 'monospace',
    background: '#e9ecef',
    padding: '2px 8px',
    borderRadius: '4px',
    fontSize: '12px',
  },
  // Progress
  progress: {
    fontSize: '14px',
    color: '#666',
    marginTop: '6px',
  },
  progressBar: {
    height: '6px',
    background: '#e9ecef',
    borderRadius: '3px',
    marginTop: '10px',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    background: '#0066cc',
    borderRadius: '3px',
    transition: 'width 0.3s ease',
  },
  // Results table
  tableWrapper: {
    overflowX: 'auto',
    borderRadius: '6px',
    border: '1px solid #e0e0e0',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '14px',
  },
  th: {
    background: '#f8f9fa',
    padding: '12px 14px',
    textAlign: 'left',
    fontWeight: '600',
    color: '#444',
    borderBottom: '2px solid #dee2e6',
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '11px 14px',
    borderBottom: '1px solid #f0f0f0',
    color: '#333',
    verticalAlign: 'top',
  },
  tdMono: {
    fontFamily: 'monospace',
    fontSize: '13px',
    color: '#333',
  },
  tdPrice: {
    fontWeight: '600',
    color: '#1565c0',
  },
  tdMargin: {
    fontWeight: '600',
    color: '#2e7d32',
  },
  tdReasoning: {
    maxWidth: '260px',
    lineHeight: '1.5',
    color: '#555',
    fontSize: '13px',
  },
  badgeSuccess: {
    background: '#d4edda',
    color: '#155724',
    padding: '2px 10px',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: '600',
    whiteSpace: 'nowrap',
  },
  badgeError: {
    background: '#f8d7da',
    color: '#721c24',
    padding: '2px 10px',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: '600',
    whiteSpace: 'nowrap',
  },
  // Summary stats
  statsRow: {
    display: 'flex',
    gap: '16px',
    marginBottom: '20px',
    flexWrap: 'wrap',
  },
  statCard: {
    flex: 1,
    minWidth: '120px',
    background: '#f8f9fa',
    borderRadius: '8px',
    padding: '14px 18px',
    textAlign: 'center',
  },
  statValue: {
    fontSize: '26px',
    fontWeight: '700',
    color: '#1a1a2e',
  },
  statLabel: {
    fontSize: '12px',
    color: '#888',
    marginTop: '4px',
  },
  // CSV hint
  hint: {
    background: '#e8f4fd',
    border: '1px solid #bee5f9',
    borderRadius: '6px',
    padding: '12px 16px',
    fontSize: '13px',
    color: '#1565c0',
    marginTop: '16px',
  },
  // Polling indicator
  pollingDot: {
    display: 'inline-block',
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: '#0066cc',
    marginRight: '8px',
    animation: 'pulse 1.2s infinite',
  },
}

// ===========================================================================
// 辅助函数
// ===========================================================================
const STATUS_TEXT = {
  pending:    '⏳ 等待中 — 任务已创建，即将开始处理',
  processing: '⚙️ 处理中 — 正在逐个 SKU 调用 AI 定价',
  completed:  '✅ 定价完成',
  failed:     '❌ 任务失败',
}

function getStatusText(status) {
  return STATUS_TEXT[status] || status?.toUpperCase() || '未知'
}

function getStatusStyle(status) {
  return { ...styles.statusBanner, ...(styles[`status_${status}`] || {}) }
}

function formatPrice(val) {
  if (val == null) return '—'
  return `$${Number(val).toFixed(2)}`
}

function formatMargin(val) {
  if (val == null) return '—'
  return `${(Number(val) * 100).toFixed(1)}%`
}

// ===========================================================================
// 主组件
// ===========================================================================
function App() {
  const [file, setFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)

  const [pricingData, setPricingData] = useState(null)   // GET /api/pricing/<id>/ response
  const [polling, setPolling] = useState(false)
  const pollingRef = useRef(null)
  const fileInputRef = useRef(null)

  // ── Polling effect ────────────────────────────────────────────────────────
  useEffect(() => {
    const isActive = polling &&
      pricingData?.request_id &&
      (pricingData.status === 'pending' || pricingData.status === 'processing')

    if (isActive) {
      pollingRef.current = setInterval(async () => {
        try {
          const res = await fetch(`/api/pricing/${pricingData.request_id}/`)
          const data = await res.json()
          setPricingData(data)
          if (data.status === 'completed' || data.status === 'failed') {
            setPolling(false)
          }
        } catch {
          // 网络错误时继续等待，不停止轮询
        }
      }, 2000)
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }
  }, [polling, pricingData?.request_id, pricingData?.status])

  // ── 文件选择 ──────────────────────────────────────────────────────────────
  const handleFileSelect = (f) => {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.csv')) {
      setUploadError('请选择 .csv 格式的文件')
      return
    }
    setFile(f)
    setUploadError(null)
  }

  const handleDragOver = (e) => { e.preventDefault(); setDragOver(true) }
  const handleDragLeave = () => setDragOver(false)
  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleFileSelect(e.dataTransfer.files[0])
  }

  // ── 上传 ──────────────────────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!file || uploading) return

    setUploading(true)
    setUploadError(null)
    setPricingData(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch('/api/pricing/upload/', { method: 'POST', body: formData })
      const data = await res.json()

      if (!res.ok) {
        setUploadError(data.error || `上传失败（HTTP ${res.status}）`)
        return
      }

      // 上传成功 → 立刻拉一次完整详情（含 results 字段）
      const detailRes = await fetch(`/api/pricing/${data.request_id}/`)
      const detailData = await detailRes.json()
      setPricingData(detailData)
      setPolling(true)
    } catch (err) {
      setUploadError('网络错误：' + err.message)
    } finally {
      setUploading(false)
    }
  }

  // ── 下载 ──────────────────────────────────────────────────────────────────
  const handleDownload = () => {
    if (pricingData?.request_id) {
      window.location.href = `/api/pricing/${pricingData.request_id}/download/`
    }
  }

  // ── 重置 ──────────────────────────────────────────────────────────────────
  const handleReset = () => {
    setFile(null)
    setUploadError(null)
    setPricingData(null)
    setPolling(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // ── 计算统计数据 ──────────────────────────────────────────────────────────
  const results = pricingData?.results || []
  const successCount = results.filter(r => !r.error_message).length
  const errorCount   = results.filter(r =>  r.error_message).length
  const avgPrice = successCount > 0
    ? results.reduce((s, r) => s + (r.recommended_price || 0), 0) / successCount
    : null
  const avgMargin = successCount > 0
    ? results.reduce((s, r) => s + (r.expected_margin || 0), 0) / successCount
    : null

  // ── 渲染 ──────────────────────────────────────────────────────────────────
  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <h1 style={styles.header}>🏷️ AI 智能定价系统</h1>
        <p style={styles.subtitle}>
          上传包含 SKU ID 的 CSV 文件，AI 自动从知识库检索商品信息并生成定价建议
        </p>

        {/* ===================== 上传区（未上传时显示）===================== */}
        {!pricingData && (
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>上传 SKU 清单</h2>

            {/* 拖拽区 */}
            <div
              style={{
                ...styles.dropzone,
                ...(dragOver ? styles.dropzoneActive : {}),
                ...(file ? styles.dropzoneHasFile : {}),
              }}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                style={{ display: 'none' }}
                onChange={(e) => handleFileSelect(e.target.files[0])}
              />
              {file ? (
                <>
                  <div style={styles.dropzoneIcon}>📄</div>
                  <div style={{ ...styles.dropzoneText, color: '#28a745' }}>{file.name}</div>
                  <div style={styles.dropzoneHint}>
                    {(file.size / 1024).toFixed(1)} KB — 点击重新选择
                  </div>
                </>
              ) : (
                <>
                  <div style={styles.dropzoneIcon}>📂</div>
                  <div style={styles.dropzoneText}>点击选择文件 或 拖拽 CSV 至此处</div>
                  <div style={styles.dropzoneHint}>支持 .csv 格式，请确保包含 sku_id 列</div>
                </>
              )}
            </div>

            {/* 错误提示 */}
            {uploadError && (
              <div style={{ ...getStatusStyle('failed'), marginBottom: '16px', textAlign: 'left' }}>
                ⚠️ {uploadError}
              </div>
            )}

            {/* 上传按钮 */}
            <button
              style={{
                ...styles.button,
                ...(!file || uploading ? styles.buttonDisabled : {}),
              }}
              onClick={handleUpload}
              disabled={!file || uploading}
            >
              {uploading ? '⏳ 上传中...' : '🚀 开始 AI 定价分析'}
            </button>

            {/* CSV 格式说明 */}
            <div style={styles.hint}>
              <strong>CSV 格式说明：</strong>第一行为表头，必须包含 <code>sku_id</code> 列。
              示例：<code>sku_id,备注</code> / <code>ELE-001,无线耳机</code>
            </div>
          </div>
        )}

        {/* ===================== 结果区（上传后显示）===================== */}
        {pricingData && (
          <div style={styles.card}>
            {/* 请求信息栏 */}
            <div style={styles.requestInfo}>
              <span>📁 <strong>{pricingData.uploaded_filename}</strong></span>
              <span>共 <strong>{pricingData.sku_count}</strong> 个 SKU</span>
              <span style={styles.requestId}>ID: {pricingData.request_id.substring(0, 8)}…</span>
              <span style={{ color: '#999', marginLeft: 'auto', fontSize: '12px' }}>
                {new Date(pricingData.created_at).toLocaleString('zh-CN')}
              </span>
            </div>

            {/* 状态 Banner */}
            <div style={getStatusStyle(pricingData.status)}>
              <strong>{getStatusText(pricingData.status)}</strong>
              {(pricingData.status === 'pending' || pricingData.status === 'processing') && (
                <div style={styles.progress}>
                  已处理 {pricingData.completed_count || 0} / {pricingData.sku_count} 个 SKU
                  <div style={styles.progressBar}>
                    <div style={{
                      ...styles.progressFill,
                      width: `${pricingData.sku_count > 0
                        ? Math.round((pricingData.completed_count || 0) / pricingData.sku_count * 100)
                        : 0}%`
                    }} />
                  </div>
                  <div style={{ marginTop: '8px', fontSize: '12px' }}>
                    <span style={styles.pollingDot} />
                    每 2 秒自动刷新…
                  </div>
                </div>
              )}
              {pricingData.status === 'failed' && pricingData.error_message && (
                <div style={{ marginTop: '8px', fontSize: '13px' }}>
                  错误：{pricingData.error_message}
                </div>
              )}
            </div>

            {/* 汇总统计（completed 时显示）*/}
            {pricingData.status === 'completed' && results.length > 0 && (
              <div style={styles.statsRow}>
                <div style={styles.statCard}>
                  <div style={styles.statValue}>{pricingData.sku_count}</div>
                  <div style={styles.statLabel}>总 SKU 数</div>
                </div>
                <div style={styles.statCard}>
                  <div style={{ ...styles.statValue, color: '#2e7d32' }}>{successCount}</div>
                  <div style={styles.statLabel}>定价成功</div>
                </div>
                <div style={styles.statCard}>
                  <div style={{ ...styles.statValue, color: '#c62828' }}>{errorCount}</div>
                  <div style={styles.statLabel}>未找到</div>
                </div>
                {avgPrice != null && (
                  <div style={styles.statCard}>
                    <div style={styles.statValue}>${avgPrice.toFixed(2)}</div>
                    <div style={styles.statLabel}>平均建议价</div>
                  </div>
                )}
                {avgMargin != null && (
                  <div style={styles.statCard}>
                    <div style={styles.statValue}>{(avgMargin * 100).toFixed(1)}%</div>
                    <div style={styles.statLabel}>平均毛利率</div>
                  </div>
                )}
              </div>
            )}

            {/* 结果明细表 */}
            {results.length > 0 && (
              <div style={styles.tableWrapper}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>SKU ID</th>
                      <th style={styles.th}>建议价 (USD)</th>
                      <th style={styles.th}>最低价</th>
                      <th style={styles.th}>最高价</th>
                      <th style={styles.th}>预期毛利率</th>
                      <th style={styles.th}>定价依据</th>
                      <th style={styles.th}>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((r, idx) => (
                      <tr
                        key={r.result_id}
                        style={{ background: idx % 2 === 0 ? '#fff' : '#fafafa' }}
                      >
                        <td style={{ ...styles.td, ...styles.tdMono }}>{r.sku_id}</td>
                        <td style={{ ...styles.td, ...styles.tdPrice }}>
                          {formatPrice(r.recommended_price)}
                        </td>
                        <td style={styles.td}>{formatPrice(r.price_min)}</td>
                        <td style={styles.td}>{formatPrice(r.price_max)}</td>
                        <td style={{ ...styles.td, ...styles.tdMargin }}>
                          {formatMargin(r.expected_margin)}
                        </td>
                        <td style={{ ...styles.td, ...styles.tdReasoning }}>
                          {r.error_message
                            ? <span style={{ color: '#c62828' }}>{r.error_message}</span>
                            : r.reasoning
                          }
                        </td>
                        <td style={styles.td}>
                          {r.error_message
                            ? <span style={styles.badgeError}>未找到</span>
                            : <span style={styles.badgeSuccess}>成功</span>
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* 操作按钮 */}
            <div style={styles.buttonRow}>
              {pricingData.status === 'completed' && (
                <button style={styles.downloadButton} onClick={handleDownload}>
                  ⬇️ 下载结果 CSV
                </button>
              )}
              <button style={styles.resetButton} onClick={handleReset}>
                🔄 重新上传
              </button>
            </div>
          </div>
        )}
      </div>

      {/* CSS 动画（轮询闪烁点）*/}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.2; }
        }
      `}</style>
    </div>
  )
}

export default App
