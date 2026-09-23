import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "./ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from "./ui/dropdown-menu";
import {
  BarChart3,
  BookOpen,
  Settings,
  User,
  LogOut,
  Menu,
  X,
  ChevronLeft,
  ChevronRight,
  Users,
  BellIcon,
} from "lucide-react";
import { cn } from "./ui/utils";
import { toast } from "sonner";
import { authService } from "../service/auth";
import { getUserInfoFromToken } from "../utils/jwt";

export type NavigationPage = "overview" | "alerts" | "runbooks" | "setup" | "users";

interface AppShellProps {
  children: React.ReactNode;
}

const navigationItems = [
  {
    id: "overview" as NavigationPage,
    label: "Overview",
    icon: BarChart3,
    path: "/overview"
  },
  {
    id: "alerts" as NavigationPage,
    label: "Alerts",
    icon: BellIcon,
    path: "/alerts"
  },
  {
    id: "runbooks" as NavigationPage,
    label: "Runbooks",
    icon: BookOpen,
    path: "/runbooks"
  },
  {
    id: "setup" as NavigationPage,
    label: "Setup",
    icon: Settings,
    path: "/setup"
  }
];

const adminNavigationItems = [
  {
    id: "users" as NavigationPage,
    label: "Users",
    icon: Users,
    path: "/users",
    adminOnly: true
  }
];

export function AppShell({ children }: AppShellProps) {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // Get current user info to check if admin
  const currentUserInfo = getUserInfoFromToken();
  const isAdmin = currentUserInfo?.admin || false;

  // Combine navigation items based on admin status
  const allNavigationItems = isAdmin
    ? [...navigationItems, ...adminNavigationItems]
    : navigationItems;

  const handleLogout = async () => {
    try {
      await authService.logout();
      toast.success("Logged out successfully!");
      navigate("/login");
    } catch (error) {
      console.error("Logout error:", error);
      // Still navigate to login even if API call fails
      toast.success("Logged out successfully!");
      navigate("/login");
    }
  };

  return (
    <div className="bg-surface">
      {/* Top App Bar */}
      <header className="bg-card px-6 flex items-center justify-between sticky top-0 z-50 shadow-sm border-b border-border-medium" style={{height: 'var(--header-height)'}}>
        {/* Left: Product Name + Mobile Menu */}
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            className="md:hidden"
            onClick={() => setIsMobileNavOpen(!isMobileNavOpen)}
          >
            {isMobileNavOpen ? <X className="h-5 w-5 text-success" /> : <Menu className="h-5 w-5 text-foreground" />}
          </Button>
          <div className="flex items-center gap-2">
            <h1 className="text-header text-foreground">OR<span className="text-primary text-header">I</span>AN CLOUDMAX</h1>
          </div>
        </div>

        {/* Right: Action Icons + User Menu */}
        <div className="flex items-center gap-2">

          {/* User Avatar */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-full bg-gradient-green text-white hover:opacity-90 transition-opacity"
              >
                <span className="text-sm font-semibold">{currentUserInfo?.username?.slice(0,2)?.toUpperCase()}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56" align="end" forceMount>
              <DropdownMenuItem onClick={() => navigate("/profile")}>
                <User className="mr-2 h-4 w-4" />
                <span>Profile</span>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleLogout}>
                <LogOut className="mr-2 h-4 w-4" />
                <span>Log out</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <div className="flex box-shadow" style={{minHeight:"var(--content-height)"}} >
        {/* Left Navigation */}
        <nav
          className={cn(
            "bg-card box-shadow border-border-medium h-full transition-all duration-200 ease-in-out relative overflow-visible",
            "md:translate-x-0 md:relative md:z-20",
            isMobileNavOpen ? "translate-x-0 fixed z-40 w-64" : "-translate-x-full fixed z-40 w-64",
            // Desktop collapsed/expanded states
            "md:translate-x-0",
            isSidebarCollapsed ? "md:w-16" : "md:w-64"
          )}
          style={{height: 'var(--content-height)'}}
          >
          <div className={cn(
            "p-4 space-y-2",
            isSidebarCollapsed && "md:p-2"
          )}>
            {allNavigationItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path || (item.path !== "/overview" && location.pathname.startsWith(item.path));

              return (
                <Link
                  key={item.id}
                  to={item.path}
                  className={cn(
                    "flex items-center w-full gap-3 transition-all duration-200 px-3 py-4 rounded-lg text-md font-medium",
                    isActive
                      ? "bg-gradient-green font-bold text-white shadow-sm"
                      : "text-foreground hover:bg-surface-hover hover:text-foreground",
                    isSidebarCollapsed ? "md:justify-center md:px-2" : "justify-start"
                  )}
                  onClick={() => setIsMobileNavOpen(false)}
                  title={isSidebarCollapsed ? item.label : undefined}
                >
                  <Icon className="h-5 w-5 flex-shrink-0" />
                  <span className={cn(
                    "transition-all duration-200",
                    isSidebarCollapsed && "md:hidden"
                  )}>
                    {item.label}
                  </span>
                  {isActive && !isSidebarCollapsed ? (<span className="h-3 w-3 rounded-full bg-background ml-auto"></span>) :null}
                </Link>
              );
            })}
          </div>
          
          {/* Sidebar Toggle Button - Desktop Only */}
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "hidden md:flex absolute -right-3 top-4 w-6 h-6 p-0 rounded-full bg-surface border border-border-medium shadow-sm hover:bg-surface-hover z-10",
              "transition-all duration-200"
            )}
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          >
            {isSidebarCollapsed ? (
              <ChevronRight className="h-3 w-3 text-foreground" />
            ) : (
              <ChevronLeft className="h-3 w-3 text-foreground" />
            )}
          </Button>
        </nav>

        {/* Mobile Overlay */}
        {isMobileNavOpen && (
          <div 
            className="fixed inset-0 bg-black bg-opacity-50 z-30 md:hidden"
            onClick={() => setIsMobileNavOpen(false)}
          />
        )}

        {/* Main Content Area */}
        <main
          className="flex-1 min-w-0 overflow-auto"
          style={{
            height: 'var(--content-height)',
            scrollBehavior: 'smooth',
            WebkitOverflowScrolling: 'touch',
            willChange: 'scroll-position'
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}