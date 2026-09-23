import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { toast } from "sonner";
import { authService, UserProfile } from "../../service/auth";
import { getUserIdFromToken } from "../../utils/jwt";
import { Loader2, Lock, InfoIcon } from "lucide-react";

export function Profile() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUpdatingPassword, setIsUpdatingPassword] = useState(false);
  const [showPasswordForm, setShowPasswordForm] = useState(false);

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    // Get user ID from JWT token
    const userId = getUserIdFromToken();

    if (!userId) {
      toast.error("User ID not found. Please log in again.");
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      const userProfile = await authService.getUserProfile(userId);
      setProfile(userProfile);
    } catch (error: any) {
      console.error("Failed to load profile:", error);
      toast.error(error.message || "Failed to load profile");
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate passwords match
    if (newPassword !== confirmNewPassword) {
      toast.error("New passwords do not match");
      return;
    }

    // Validate password strength
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters long");
      return;
    }

    // Validate old and new passwords are different
    if (oldPassword === newPassword) {
      toast.error("New password must be different from old password");
      return;
    }

    setIsUpdatingPassword(true);

    try {
      await authService.updatePassword({
        old_password: oldPassword,
        new_password: newPassword,
      });

      toast.success("Password updated successfully!");

      // Reset form
      setOldPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      setShowPasswordForm(false);
    } catch (error: any) {
      console.error("Password update error:", error);
      toast.error(error.message || "Failed to update password");
    } finally {
      setIsUpdatingPassword(false);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return "N/A";
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  };

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[400px]">
        <div className="flex items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-muted" />
          <span className="text-secondary">Loading profile...</span>
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[400px]">
        <p className="text-muted-foreground">Failed to load profile</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Profile Information Card */}
      <h1 className="page-title font-bold title-lg-header">Profile</h1>
      <Card className="box-shadow p-6">
        <CardTitle className="flex card-title">
          <InfoIcon size={16} className="mt-1 mr-2"/>
          Profile Information
        </CardTitle>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-muted-foreground flex items-center gap-2">
                Username
              </Label>
              <p className="font-medium">{profile.username}</p>
            </div>
            {profile.created_at && (
              <div className="space-y-2">
                <Label className="text-muted-foreground flex items-center gap-2">
                  Member Since
                </Label>
                <p className="font-medium">{formatDate(profile.created_at)}</p>
              </div>
            )}
            
            <div className="space-y-2">
              <Label className="text-muted-foreground flex items-center gap-2">
                Email
              </Label>
              <p className="font-medium">{profile.email}</p>
            </div>
            
            {profile.updated_at && (
              <div className="space-y-2">
                <Label className="text-muted-foreground flex items-center gap-2">
                  Last Updated
                </Label>
                <p className="font-medium">{formatDate(profile.updated_at)}</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Password Update Card */}
      <Card className="box-shadow">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 card-title">
            <Lock className="h-5 w-5" />
            Update Password
          </CardTitle>
        </CardHeader>
        <CardContent style={{width:400}}>
          {!showPasswordForm ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Keep your account secure by regularly updating your password.
              </p>
              <Button className="active-range-bg" onClick={() => setShowPasswordForm(true)}>
                Change Password
              </Button>
            </div>
          ) : (
            <form onSubmit={handleUpdatePassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="oldPassword">Old Password <span className="text-red-600">*</span></Label>
                <Input
                  id="oldPassword"
                  type="password"
                  placeholder="Enter current password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="newPassword">New Password  <span className="text-red-600">*</span></Label>
                <Input
                  id="newPassword"
                  type="password"
                  placeholder="Enter new password (min. 8 characters)"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={8}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmNewPassword">Confirm New Password  <span className="text-red-600">*</span></Label>
                <Input
                  id="confirmNewPassword"
                  type="password"
                  placeholder="Re-enter new password"
                  value={confirmNewPassword}
                  onChange={(e) => setConfirmNewPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={8}
                />
              </div>
              <div className="flex gap-2">
                <Button type="submit" className="active-range-bg" disabled={isUpdatingPassword}>
                  {isUpdatingPassword ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Updating...
                    </>
                  ) : (
                    "Update Password"
                  )}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowPasswordForm(false);
                    setOldPassword("");
                    setNewPassword("");
                    setConfirmNewPassword("");
                  }}
                  disabled={isUpdatingPassword}
                >
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
