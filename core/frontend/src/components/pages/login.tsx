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


export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      // Call the real login API
      await authService.login({ email, password });

      toast.success("Login successful!");
      navigate("/overview");
    } catch (error: any) {
      console.error("Login error:", error);
      toast.error(error.message || "Login failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid grid-cols-2" >
      {/* Left Column - Login Form */}
      <div className="bg-white flex flex-col p-8">
        <div className="mb-8">
          <div className="absolute flex items-center gap-2" style={{top: '40px', left: '40px'}}>
            <h1 className="text-header text-foreground">OR<span className="text-primary text-header">I</span>AN CLOUDMAX</h1>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-md space-y-8 box-shadow p-6">
            <div className="space-y-2">
              <h2 className="page-title font-bold text-center">Login</h2>
              <p className="text-sm text-gray-600">
                Enter your credentials to access the dashboard
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">

              <div className="space-y-2">
                <Label htmlFor="email" className="text-sm font-medium">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="Enter username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
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
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={isLoading}
                />
                {/* <div className="flex justify-end">
                  <Link
                    to="/forgot-password"
                    className="text-xs text-gray-600 hover:text-gray-900"
                  >
                    Forgot Password
                  </Link>
                </div> */}
              </div>

              <Button
                type="submit"
                disabled={isLoading}
                className="w-full h-11 bg-teal-600 hover:bg-teal-700 text-white bg-primary"
              >
                {isLoading ? "Signing in..." : "Sign In"}
              </Button>

              <div className="text-center text-sm">
                <span className="text-gray-600">Don't have an account? </span>
                <Link
                  to="/register"
                  className="hover:underline font-medium text-primary"
                >
                  Create account
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