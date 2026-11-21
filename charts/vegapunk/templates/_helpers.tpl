{{/* Env shared by the web and indexer containers. */}}
{{- define "vegapunk.env" -}}
- name: NODE_ENV
  value: production
- name: DOCS_DIR
  value: /data/nextcloud
- name: QDRANT_URL
  value: http://{{ .Release.Name }}-qdrant:{{ .Values.qdrant.service.port }}
- name: QDRANT_COLLECTION
  value: {{ .Values.qdrant.collection | quote }}
- name: LLM_BASE_URL
  value: {{ .Values.config.llmBaseUrl | quote }}
- name: LLM_MODEL
  value: {{ .Values.config.llmModel | quote }}
- name: CF_ACCESS_TEAM_DOMAIN
  value: {{ .Values.config.cfAccessTeamDomain | quote }}
- name: CF_ACCESS_ALLOWED_EMAILS
  value: {{ .Values.config.cfAccessAllowedEmails | quote }}
{{- range .Values.env }}
- name: {{ .name }}
  value: {{ .value | quote }}
{{- end }}
{{- range .Values.secretEnv }}
- name: {{ .name }}
  valueFrom:
    secretKeyRef:
      name: {{ $.Values.secretName }}
      key: {{ .key }}
      optional: true
{{- end }}
{{- end -}}

{{/* Pod-level security: non-root uid 1000 (the image's `bun` user), PVC writable via fsGroup. */}}
{{- define "vegapunk.podSecurity" -}}
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
{{- end -}}
