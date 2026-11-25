import type { Alternative, Catalog, Course, CourseInput, MutationResult, Preferences, Section, SectionInput, Session, SessionInput } from './types'

export class ApiError extends Error {
  constructor(message: string, public field?: string, public status?: number) { super(message) }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const csrf = document.cookie.split('; ').find(item => item.startsWith('unischedule_csrf='))?.split('=')[1]
  const mutating = options?.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase())
  const response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(mutating && csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}), ...options?.headers } })
  if (!response.ok) {
    if (response.status === 401 && window.location.pathname.startsWith('/admin/dashboard')) {
      window.location.replace('/admin')
      throw new ApiError('Admin sign-in required.', undefined, 401)
    }
    const body = await response.json().catch(() => ({}))
    if (body.detail && typeof body.detail === 'object' && !Array.isArray(body.detail)) throw new ApiError(body.detail.message || 'Please check this field.', body.detail.field, response.status)
    if (Array.isArray(body.detail)) {
      const issue = body.detail[0]
      throw new ApiError(issue?.msg || 'Please check the form.', issue?.loc?.at(-1), response.status)
    }
    throw new ApiError(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`, undefined, response.status)
  }
  return response.json() as Promise<T>
}

export const api = {
  adminMe: () => request<{ username: string }>('/admin/me'),
  adminLogin: (username: string, password: string) => request<{ username: string }>('/admin/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  adminLogout: () => request<{ message: string }>('/admin/logout', { method: 'POST' }),
  adminLegacy: () => request<{ saved_schedules: number }>('/admin/legacy'),
  adminClaimLegacy: () => request<{ imported: number }>('/admin/claim-legacy', { method: 'POST' }),
  catalog: () => request<Catalog>('/catalog'),
  preferences: () => request<Preferences>('/preferences'),
  updatePreferences: (data: Preferences) => request<Preferences>('/preferences', { method: 'PUT', body: JSON.stringify(data) }),
  generate: () => request<{ alternatives: Alternative[] }>('/generate', { method: 'POST' }),
  schedules: () => request<Alternative[]>('/schedules'),
  saveSchedule: (name: string, section_ids: number[]) => request<Alternative>('/schedules', { method: 'POST', body: JSON.stringify({ name, section_ids }) }),
  courses: () => request<Course[]>('/courses'),
  archivedCourses: () => request<Course[]>('/courses/archived'),
  course: (id: number) => request<Course>(`/courses/${id}`),
  addCourse: (data: CourseInput) => request<Course>('/courses', { method: 'POST', body: JSON.stringify(data) }),
  updateCourse: (id: number, data: CourseInput) => request<Course & { affected_schedules: number }>(`/courses/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCourse: (id: number) => request<MutationResult>(`/courses/${id}`, { method: 'DELETE' }),
  restoreCourse: (id: number) => request<Course & { affected_schedules: number }>(`/courses/${id}/restore`, { method: 'POST' }),
  sections: (courseId: number) => request<Section[]>(`/courses/${courseId}/sections`),
  section: (id: number) => request<Section>(`/sections/${id}`),
  addSection: (courseId: number, data: SectionInput) => request<Section>(`/courses/${courseId}/sections`, { method: 'POST', body: JSON.stringify(data) }),
  updateSection: (id: number, data: SectionInput) => request<Section & { affected_schedules: number }>(`/sections/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteSection: (id: number) => request<MutationResult>(`/sections/${id}`, { method: 'DELETE' }),
  sessions: (sectionId: number) => request<Session[]>(`/sections/${sectionId}/sessions`),
  session: (id: number) => request<Session>(`/sessions/${id}`),
  addSession: (sectionId: number, data: SessionInput) => request<Session & { affected_schedules: number }>(`/sections/${sectionId}/sessions`, { method: 'POST', body: JSON.stringify(data) }),
  updateSession: (id: number, data: SessionInput) => request<Session & { affected_schedules: number }>(`/sessions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteSession: (id: number) => request<MutationResult>(`/sessions/${id}`, { method: 'DELETE' }),
}
