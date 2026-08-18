/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_DEMO_ORG_ID?: string;
  readonly VITE_DEMO_TEACHER_ID?: string;
  readonly VITE_DEMO_STUDENT_ID?: string;
  readonly VITE_DEMO_CLASS_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
