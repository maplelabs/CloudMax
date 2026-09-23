interface LoaderProps {
    className?: string;
}

export default function Loader({ className }: LoaderProps) {
    return (
        <svg className={className} width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
            <g clipPath="url(#clip0_1439_889)">
                <path d="M6 1V3" stroke="currentColor" strokeWidth="1.22614" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M8.09985 3.9002L9.54985 2.4502" stroke="currentColor" strokeWidth="1.22614" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M9 6H11" stroke="currentColor" strokeWidth="1.22614" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M8.09985 8.09961L9.54985 9.54961" stroke="currentColor" strokeWidth="1.22614" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M6 9V11" stroke="currentColor" strokeWidth="1.22614" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2.44995 9.54961L3.89995 8.09961" stroke="currentColor" strokeWidth="1.22614" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M1 6H3" stroke="currentColor" strokeWidth="1.22614" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2.44995 2.4502L3.89995 3.9002" stroke="currentColor" strokeWidth="1.22614" strokeLinecap="round" strokeLinejoin="round" />
            </g>
            <defs>
                <clipPath id="clip0_1439_889">
                    <rect width="12" height="12" fill="white" />
                </clipPath>
            </defs>
        </svg>

    )
}
