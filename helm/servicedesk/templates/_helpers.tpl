{{- define "servicedesk.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "servicedesk.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "servicedesk.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "servicedesk.labels" -}}
helm.sh/chart: {{ include "servicedesk.chart" . }}
app.kubernetes.io/name: {{ include "servicedesk.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/part-of: servicedesk
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "servicedesk.backend.selectorLabels" -}}
app: servicedesk-backend
app.kubernetes.io/name: {{ include "servicedesk.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
{{- end }}

{{- define "servicedesk.frontend.selectorLabels" -}}
app: servicedesk-frontend
app.kubernetes.io/name: {{ include "servicedesk.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "servicedesk.postgres.selectorLabels" -}}
app: servicedesk-postgres
app.kubernetes.io/name: {{ include "servicedesk.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: database
{{- end }}

{{- define "servicedesk.postgres.secretName" -}}
{{ include "servicedesk.fullname" . }}-postgres
{{- end }}

{{- define "servicedesk.postgres.host" -}}
{{ include "servicedesk.fullname" . }}-postgres
{{- end }}

{{- define "servicedesk.databaseUrl" -}}
postgresql+psycopg://{{ .Values.postgres.username }}:{{ .Values.postgres.password }}@{{ include "servicedesk.postgres.host" . }}:{{ .Values.postgres.port }}/{{ .Values.postgres.database }}
{{- end }}

{{- define "servicedesk.backend.replicas" -}}
{{- default .Values.replicaCount .Values.backend.replicas -}}
{{- end }}

{{- define "servicedesk.frontend.replicas" -}}
{{- default .Values.replicaCount .Values.frontend.replicas -}}
{{- end }}
