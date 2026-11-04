/** Sections that exist in the navigation but are not implemented yet. Their content is taken from the roadmap
 *  (docs/ARCHITECTURE.md §12) so the UI never implies functionality that is not there. */
export interface LabInfo {
  path: string
  title: string
  phase: number
  summary: string
  planned: string[]
  /** Dependency names (as reported by /api/system/dependencies) this lab will rely on. */
  needs: string[]
  caveat?: string
}

export const LABS: LabInfo[] = [
  {
    path: 'image',
    title: 'Image Lab',
    phase: 3,
    summary: 'Structure, LSB and statistical analysis of still images.',
    planned: [
      'PNG chunk / CRC and JPEG marker inspection, trailing-data detection',
      'LSB extraction with configurable channel, bit position, bit order, traversal and offset',
      'Interactive bit-plane viewer with pixel inspection and export',
      'Histograms, entropy, chi-square and local anomaly maps',
      'Embedded file carving (ZIP / PDF / image signatures) with safe extraction',
    ],
    needs: ['pillow', 'numpy', 'scipy', 'opencv', 'scikit-image', 'construct', 'binwalk'],
    caveat: 'Pixel-LSB methods do not apply to JPEG DCT-domain steganography; statistical tests are heuristics, not proof.',
  },
  {
    path: 'audio',
    title: 'Audio Lab',
    phase: 4,
    summary: 'Waveform, spectrogram and PCM analysis.',
    planned: [
      'Zoomable waveform with silence / clipping detection',
      'STFT spectrogram with FFT size, hop, scale and range controls',
      'PCM LSB extraction (WAV / AIFF / FLAC) with channel and bit options',
      'FFT spectrum and band / high / low-pass filtering into derived copies',
      'WAV chunk and appended-data inspection',
    ],
    needs: ['librosa', 'soundfile', 'mutagen', 'numpy', 'scipy', 'ffmpeg'],
    caveat: 'Bit-exact LSB recovery is not possible from lossy codecs (MP3, AAC, OGG, Opus).',
  },
  {
    path: 'video',
    title: 'Video Lab',
    phase: 5,
    summary: 'Container, frame and temporal analysis of video files.',
    planned: [
      'Container / stream / subtitle / attachment inspection via ffprobe',
      'Frame browser, thumbnails, contact sheets, duplicate-frame detection',
      'Image-lab techniques applied to selected frames or intervals',
      'Frame-difference and scene-transition analysis',
      'Audio stream extraction handed to the Audio Lab with provenance',
    ],
    needs: ['ffmpeg', 'ffprobe', 'opencv', 'pyav', 'numpy'],
    caveat: 'Frame-level analysis is only trustworthy for lossless or near-lossless sources.',
  },
  {
    path: 'metadata',
    title: 'Metadata Explorer',
    phase: 2,
    summary: 'Universal format identification and metadata inspection.',
    planned: [
      'Real-format identification with extension-mismatch detection',
      'EXIF, XMP, IPTC, PNG text chunks, ICC profiles, audio tags, video metadata',
      'Raw next to parsed values, JSON export and search',
      'Detection of encoded strings, hidden URLs and unusual timestamps',
    ],
    needs: ['python-magic', 'exiftool', 'mutagen', 'construct', 'ffprobe', 'pillow'],
  },
  {
    path: 'payload',
    title: 'Payload Extractor',
    phase: 7,
    summary: 'Workspace for extracted bytes and their provenance.',
    planned: [
      'Export, decode and hash extracted bytes; identify extracted file types',
      'Open extracted files as new evidence with a parent link',
      'Extraction history with offsets, configuration and confidence',
    ],
    needs: ['binwalk', 'construct'],
  },
  {
    path: 'ctf',
    title: 'CTF Flag Hunter',
    phase: 6,
    summary: 'Pattern search over every extracted view of the evidence.',
    planned: [
      'Default and custom flag patterns / regular expressions',
      'ASCII / UTF-8 / UTF-16 / hex views and Base64 detection',
      'Every candidate shown with its source and extraction configuration',
    ],
    needs: ['yara-python'],
    caveat: 'A pattern match is a candidate, never an automatically accepted flag.',
  },
  {
    path: 'reports',
    title: 'Reports',
    phase: 8,
    summary: 'Reproducible HTML / JSON / CSV (and PDF where practical) reports.',
    planned: [
      'Evidence hashes, formats, metadata, methods, findings and limitations',
      'Confidence assessments, tool versions and audit-chain head hash',
      'Exported visualisations',
    ],
    needs: [],
  },
]
