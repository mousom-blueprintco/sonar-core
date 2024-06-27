from pydantic import BaseModel, Field
from typing import List, Optional

class ContextFilter(BaseModel):
    docs_ids: Optional[List[str]] = Field(
        None, examples=[["c202d5e6-7b69-4869-81cc-dd574ee8ee11"]]
    )
    user_id: Optional[str] = Field(
        None, examples=["102"]
    )
    project_id: Optional[str] = Field(
        None, examples=["23"]
    )
    file_id: Optional[str] = Field(
        None, examples=["a6feaf2d-101b-4eef-822e-f27e53943a4f"]
    )
    org_id: Optional[str] = Field(
        None, examples=["34"]
    )
