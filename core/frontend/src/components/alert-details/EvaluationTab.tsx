import { RefreshCw, Clock } from "lucide-react";
import { Card, CardContent } from "../ui/card";
import { MarkdownContent } from "./MarkdownContent";

interface EvaluationTabProps {
  alert: any;
  alertEvaluation: any;
  alertEvaluationLoading: boolean;
}

export const EvaluationTab = ({ alert, alertEvaluation, alertEvaluationLoading }: EvaluationTabProps) => {
  return (
    <div className="pb-6 space-y-6">
      {/* Evaluation Score Card */}
      <Card className="box-shadow rounded-lg mr-2">
        <CardContent className="p-6">
          {alertEvaluationLoading ? (
            <div className="text-center py-16">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-muted" />
              <p className="text-secondary">Loading evaluation details...</p>
            </div>
          ) : (alert.evaluation_status === "success" && alertEvaluation) ? (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 bg-success/10 rounded-lg flex items-center justify-center">
                  <svg width="46" height="46" viewBox="0 0 46 46" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <g filter="url(#filter0_dd_1099_22349)">
                      <rect x="3" y="2" width="40" height="40" rx="4" fill="#10B981" shapeRendering="crispEdges" />
                      <path d="M23 32C28.5228 32 33 27.5228 33 22C33 16.4772 28.5228 12 23 12C17.4772 12 13 16.4772 13 22C13 27.5228 17.4772 32 23 32Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M20 22L22 24L26 20" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </g>
                    <defs>
                      <filter id="filter0_dd_1099_22349" x="0" y="0" width="46" height="46" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
                        <feFlood floodOpacity="0" result="BackgroundImageFix" />
                        <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha" />
                        <feMorphology radius="1" operator="erode" in="SourceAlpha" result="effect1_dropShadow_1099_22349" />
                        <feOffset dy="1" />
                        <feGaussianBlur stdDeviation="1" />
                        <feComposite in2="hardAlpha" operator="out" />
                        <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.1 0" />
                        <feBlend mode="normal" in2="BackgroundImageFix" result="effect1_dropShadow_1099_22349" />
                        <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha" />
                        <feOffset dy="1" />
                        <feGaussianBlur stdDeviation="1.5" />
                        <feComposite in2="hardAlpha" operator="out" />
                        <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.1 0" />
                        <feBlend mode="normal" in2="effect1_dropShadow_1099_22349" result="effect2_dropShadow_1099_22349" />
                        <feBlend mode="normal" in="SourceGraphic" in2="effect2_dropShadow_1099_22349" result="shape" />
                      </filter>
                    </defs>
                  </svg>
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-foreground">Evaluation Score</h2>
                </div>
              </div>
              <div className="flex text-right justify-between">
                <div>
                  <div className="text-sm text-muted-foreground mb-1">Overall Score</div>
                  <div className="eval-tab-score" style={{ color: "#DD5E1E" }}>{Math.round(alertEvaluation.average_score_percent)}%</div>

                </div>
                {/* <div className="text-xs text-muted-foreground mt-1 px-4">
                  <span className="flex">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <g clipPath="url(#clip0_1099_22366)">
                        <path d="M4.6665 1.16699V3.50033" stroke="#64748B" strokeWidth="1.16667" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M9.3335 1.16699V3.50033" stroke="#64748B" strokeWidth="1.16667" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M11.0833 2.33301H2.91667C2.27233 2.33301 1.75 2.85534 1.75 3.49967V11.6663C1.75 12.3107 2.27233 12.833 2.91667 12.833H11.0833C11.7277 12.833 12.25 12.3107 12.25 11.6663V3.49967C12.25 2.85534 11.7277 2.33301 11.0833 2.33301Z" stroke="#64748B" strokeWidth="1.16667" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M1.75 5.83301H12.25" stroke="#64748B" strokeWidth="1.16667" strokeLinecap="round" strokeLinejoin="round" />
                      </g>
                      <defs>
                        <clipPath id="clip0_1099_22366">
                          <rect width="14" height="14" fill="white" />
                        </clipPath>
                      </defs>
                    </svg>
                    <span style={{ marginLeft: 2 }}>
                      Nov 18, 2025
                    </span>
                  </span>
                  <br />
                  <span className="flex" style={{ marginTop: 2 }}><svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <g clipPath="url(#clip0_1099_22374)">
                      <path d="M7 3.5V7L9.33333 8.16667" stroke="#64748B" strokeWidth="1.16667" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M6.99984 12.8337C10.2215 12.8337 12.8332 10.222 12.8332 7.00033C12.8332 3.77866 10.2215 1.16699 6.99984 1.16699C3.77818 1.16699 1.1665 3.77866 1.1665 7.00033C1.1665 10.222 3.77818 12.8337 6.99984 12.8337Z" stroke="#64748B" strokeWidth="1.16667" strokeLinecap="round" strokeLinejoin="round" />
                    </g>
                    <defs>
                      <clipPath id="clip0_1099_22374">
                        <rect width="14" height="14" fill="white" />
                      </clipPath>
                    </defs>
                  </svg>
                    <span style={{ marginLeft: 2 }}>2:34 PM</span></span>
                </div> */}
              </div>
            </div>
          ) : alert.evaluation_status === "processing" || alert.evaluation_status === "in-progress" ? (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-info-light rounded-full flex items-center justify-center">
                    <RefreshCw className="h-6 w-6 text-info animate-spin" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">Evaluation In Progress</h3>
                <p className="text-secondary">
                  Evaluation is currently in progress. Please check back in a few minutes to see the results.
                </p>
              </div>
            </div>
          ) : (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center">
                    <Clock className="h-6 w-6 text-muted" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">Evaluation Pending</h3>
                <p className="text-secondary">
                  Evaluation will begin after triage analysis is completed. Please check back later.
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Score Breakdown Card */}
      {alert.evaluation_status === "success" && alertEvaluation && (
        <>
          <Card className="box-shadow rounded-lg mr-2 border">
            <CardContent className="p-0">
              <h3 className="text-xl font-bold text-foreground mb-6 p-6">Score Breakdown</h3>
              <div className="space-y-6">
                {alertEvaluation.score_criteria_cards.map((criteria: any, index: number) => (
                  <div key={index} className="">
                    <div className="flex items-start justify-between mb-3 px-6">
                      <div className="flex-1 pr-6">
                        <h4 className="text-md font-semibold text-foreground mb-2">{criteria.title}</h4>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {criteria.description}
                        </p>
                      </div>
                      <div className="flex flex-col items-end gap-2" style={{ minWidth: '120px' }}>
                        <div className="text-3xl font-bold text-foreground">{Math.round(criteria.score_percent)}%</div>
                        <div className="w-32 bg-gray-200 rounded-full h-2.5">
                          <div
                            className="bg-success h-2.5 rounded-full transition-all duration-300"
                            style={{ width: `${criteria.score_percent}%` }}
                          />
                        </div>
                      </div>
                    </div>
                    {index < alertEvaluation.score_criteria_cards.length - 1 && (
                      <hr className="border-t border-gray-200 mt-6" />
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* Evaluation Summary Card */}
      {alert.evaluation_status === "success" && alertEvaluation && alertEvaluation.reason && (
        <Card className="box-shadow rounded-lg mr-2">
          <CardContent className="p-6">
            <h3 className="text-xl font-semibold text-foreground mb-6">Evaluation Summary</h3>
            <div className="prose max-w-none text-foreground leading-relaxed">
              <MarkdownContent content={alertEvaluation.reason} />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
