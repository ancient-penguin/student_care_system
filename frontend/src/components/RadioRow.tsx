// 큰 라디오 행. 판단(맞다/틀리다)과 태그 선택에 쓴다. 실제 <input type="radio">라 키보드·스크린리더로도 고를 수 있다.
type Props<T> = {
  name: string;
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (v: T) => void;
  className?: string;
};

export function RadioGroup<T extends string | boolean>({ name, options, value, onChange, className = "" }: Props<T>) {
  return (
    <div className={"radio-list " + className} role="radiogroup">
      {options.map((o) => {
        const checked = value === o.value;
        return (
          <label key={String(o.value)} className={"radio-row" + (checked ? " checked" : "")}>
            <input type="radio" name={name} checked={checked} onChange={() => onChange(o.value)} />
            <span className="radio-dot" aria-hidden />
            <span>{o.label}</span>
          </label>
        );
      })}
    </div>
  );
}
