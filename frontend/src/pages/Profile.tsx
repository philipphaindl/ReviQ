import { useState } from 'react'
import { Card, CardHeader, FormField } from '../components/ui'

export default function Profile() {
  const [saved, setSaved] = useState(false)

  function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaved(true)
    setTimeout(() => setSaved(false), 2500)
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-ink font-display">Profile</h1>
        <p className="text-sm text-ink-muted mt-1">Manage your personal information and preferences.</p>
      </div>

      {/* Avatar */}
      <Card>
        <CardHeader title="Photo" />
        <div className="flex items-center gap-5">
          <div className="w-16 h-16 rounded-full bg-accent text-white text-xl font-bold flex items-center justify-center shrink-0">
            PH
          </div>
          <div>
            <button className="btn-secondary">Upload photo</button>
            <p className="text-xs text-ink-muted mt-1.5">JPG, PNG or GIF · max 2 MB</p>
          </div>
        </div>
      </Card>

      {/* Personal info */}
      <form onSubmit={handleSave}>
        <Card>
          <CardHeader title="Personal information" />
          <div className="grid grid-cols-2 gap-4">
            <FormField label="First name" required>
              <input className="input" defaultValue="Philipp" />
            </FormField>
            <FormField label="Last name" required>
              <input className="input" defaultValue="Haindl" />
            </FormField>
          </div>
          <FormField label="Email address" required>
            <input className="input" type="email" defaultValue="philipp@example.com" />
          </FormField>
          <FormField label="Institution / Organization">
            <input className="input" placeholder="e.g. University of Vienna" />
          </FormField>
          <FormField label="Role / Title">
            <input className="input" placeholder="e.g. PhD Researcher" />
          </FormField>
          <FormField label="ORCID">
            <input className="input" placeholder="0000-0000-0000-0000" />
          </FormField>
          <div className="flex items-center gap-3 mt-2">
            <button type="submit" className="btn-primary">
              {saved ? 'Saved' : 'Save changes'}
            </button>
            {saved && <span className="text-xs text-include">Changes saved successfully.</span>}
          </div>
        </Card>
      </form>

      {/* Security */}
      <Card>
        <CardHeader title="Security" />
        <div className="space-y-3">
          <div className="flex items-center justify-between py-2 border-b border-rule">
            <div>
              <p className="text-sm font-medium text-ink">Password</p>
              <p className="text-xs text-ink-muted">Last changed 3 months ago</p>
            </div>
            <button className="btn-secondary">Change password</button>
          </div>
          <div className="flex items-center justify-between py-2">
            <div>
              <p className="text-sm font-medium text-ink">Two-factor authentication</p>
              <p className="text-xs text-ink-muted">Not enabled</p>
            </div>
            <button className="btn-secondary">Enable 2FA</button>
          </div>
        </div>
      </Card>

      {/* Danger zone */}
      <Card>
        <CardHeader title="Account" />
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-ink">Delete account</p>
            <p className="text-xs text-ink-muted">Permanently remove your account and all data.</p>
          </div>
          <button className="btn-danger">Delete account</button>
        </div>
      </Card>
    </div>
  )
}
