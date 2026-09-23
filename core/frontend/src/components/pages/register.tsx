import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { CircleCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { authService } from "../../service/auth";
//@ts-ignore
import authBgIcon from "../../icons/icon.svg";

export function Register() {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate passwords match
    if (password !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }

    // Validate password strength
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters long");
      return;
    }

    setIsLoading(true);

    try {
      // Call the registration API
      await authService.register({
        email,
        username,
        password,
      });

      toast.success("Registration successful! Please log in.");
      navigate("/login");
    } catch (error: any) {
      console.error("Registration error:", error);
      toast.error(error.message || "Registration failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid grid-cols-2">
      {/* Left Column - Register Form */}
      <div className="bg-white flex flex-col p-8">
        <div className="mb-8">
          <div className="absolute flex items-center gap-2" style={{top: '40px', left: '40px'}}>
            <h1 className="text-header text-foreground">OR<span className="text-primary text-header">I</span>AN CLOUDMAX</h1>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-md space-y-8 box-shadow p-6">
            <div className="space-y-2">
              <h2 className="page-title font-bold text-center">Create Account</h2>
              <p className="text-sm text-gray-600">
                Enter your details to create a new account
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4" autoComplete="off">
              <div className="space-y-2">
                <Label htmlFor="username" className="text-sm font-medium">
                  Username
                </Label>
                <Input
                  id="username"
                  type="text"
                  placeholder="Enter username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="off"
                  required
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email" className="text-sm font-medium">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="Enter email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="off"
                  required
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-sm font-medium">
                  Password
                </Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Enter password (min. 8 characters)"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-sm font-medium">
                  Confirm Password
                </Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  disabled={isLoading}
                />
              </div>

              <Button
                type="submit"
                disabled={isLoading}
                className="w-full h-11 bg-teal-600 hover:bg-teal-700 text-white bg-primary"
              >
                {isLoading ? "Creating account..." : "Create Account"}
              </Button>

              <div className="text-center text-sm">
                <span className="text-gray-600">Already have an account? </span>
                <Link
                  to="/login"
                  className="hover:underline font-medium text-primary"
                >
                  Sign in
                </Link>
              </div>
            </form>
          </div>
        </div>
      </div>

      {/* Right Column - Feature Showcase */}
      <div
        className="relative flex items-center justify-center p-8 text-white overflow-hidden"
        style={{
          background: `url(${authBgIcon}) no-repeat center center`,
          backgroundSize: 'cover'
        }}
      >
        <div className="relative z-10 text-center space-y-4">
          {/* Content Section */}
          <div className="space-y-6" style={{marginTop:200}}>
            <h3 className="page-title font-bold leading-tight">
              Agentic AI for SRE Ops
            </h3>
            <div style={{display:"flex", justifyContent:"center", flexDirection:"column"}}>

              <div className="flex items-start gap-2 justify-center">
                <div className="mt-1">
                  <CircleCheck size={12}/>
                </div>
                <span className="text-sm">
                  Automatic runbooks driven Alert Triaging
                </span>
              </div>

              <div className="flex items-start gap-2 py-2 justify-center">
                <div className="mt-1">
                  <CircleCheck size={12}/>
                </div>
                <span className="text-sm">
                  Real-Time Root Cause Analysis from Logs, Metrics, and Traces
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
