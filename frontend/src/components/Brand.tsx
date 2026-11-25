export default function Brand({ admin = false }: { admin?: boolean }) {
  return <div className="brand">
    <img className="brand-mark" src={`${import.meta.env.BASE_URL}halic-logo.png`} width={3000} height={3578} alt="Haliç University" />
    <strong>UniSchedule</strong>
    {admin && <span className="admin-header-label">Administration</span>}
  </div>
}
