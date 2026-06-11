from __future__ import annotations

from pathlib import Path

import numpy as np


class WavelengthMapper:
    """
    카메라의 파장(nm) 정보를 관리하는 클래스
    제조사에서 제공한 .wls 파일을 읽어와 시스템 전체에 하드웨어 파장 눈금표를 제공한다.
    """

    def __init__(self, wls_path: str | Path = "calibrations/wlcal1b_4210644.wls"): # wls 파일을 calibrations 폴더에 위치
        self.wls_path = Path(wls_path)
        self.wavelengths: np.ndarray = np.array([])
        
        # 클래스가 생성될 때 즉시 WLS 파일을 읽어 메모리에 올린다.
        self._load_wls()

    def _load_wls(self) -> None:
        """
        WLS 파일에서 중심 파장(1열)만 추출하여 1D Numpy 배열로 저장한다.
        """
        if not self.wls_path.exists():
            raise FileNotFoundError(
                f"파장 설정 파일을 찾을 수 없습니다: {self.wls_path}\n"
            )

        try:
            # usecols=0 으로 wls 파일의 첫 번째 열(중심 파장)만 가져온다. (두 번째 열은 파장 간격이므로 사용하지 않는다)
            self.wavelengths = np.loadtxt(self.wls_path, usecols=0, dtype=np.float32)
        except Exception as e:
            raise ValueError(f"WLS 파일을 읽는 중 오류가 발생했습니다: {e}")

        if len(self.wavelengths) == 0:
            raise ValueError("WLS 파일에 파장 데이터가 없습니다.")

    def get_wavelength(self, band_index: int) -> float:
        """
        주어진 밴드 인덱스(방 번호)가 물리적으로 몇 nm인지 반환한다.
        """
        if not (0 <= band_index < len(self.wavelengths)):
            raise IndexError(f"잘못된 밴드 인덱스입니다: {band_index}. (0 ~ {len(self.wavelengths)-1} 사이여야 합니다)")
        
        return float(self.wavelengths[band_index])

    def get_all_wavelengths(self) -> np.ndarray:
        """
        전체 파장 배열을 한 번에 반환한다.
        UI 스펙트럼 그래프에서 X축 전체를 그릴 때 이 함수를 호출하여 그대로 꽂아 넣으면 된다.
        """
        return self.wavelengths