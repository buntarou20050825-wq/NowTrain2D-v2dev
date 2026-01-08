// frontend/src/utils/trainUtils.js

/**
 * 任意の trip_id フォーマットから正規化された列車番号を抽出
 *
 * OTP形式 ("1:1111406H") と ODPT形式 ("4200406H") の両方に対応。
 * 末尾の 3-4桁の数字 + 英字サフィックスを抽出する。
 *
 * @param {string} tripId - OTP or リアルタイム API からの trip_id
 * @returns {string} 正規化された列車番号 (例: "406H", "1301G")
 *
 * @example
 * extractTrainNumber("1:1111406H")  // → "406H"
 * extractTrainNumber("4200406H")    // → "406H"
 * extractTrainNumber("4201301G")    // → "1301G"
 * extractTrainNumber("42000906G")   // → "906G" (先頭ゼロ除去)
 */
export function extractTrainNumber(tripId) {
  if (!tripId) return "";

  // Step 1: OTP プレフィックスを除去 ("1:1111406H" -> "1111406H")
  let cleaned = tripId;
  if (tripId.includes(":")) {
    cleaned = tripId.split(":")[1] || tripId;
  }

  // Step 2: 末尾の 3-4桁の数字 + 英字を抽出
  // パターン: 3-4桁の数字 + 1文字の英字 (大文字/小文字)
  const match = cleaned.match(/(\d{3,4})([A-Za-z])$/);

  if (match) {
    const numberPart = match[1];
    const suffix = match[2].toUpperCase();
    // 先頭のゼロを削除 ("0906" -> "906")
    const normalizedNumber = String(parseInt(numberPart, 10));
    return `${normalizedNumber}${suffix}`;
  }

  // フォールバック: クリーンアップした文字列を大文字で返す
  return cleaned.toUpperCase();
}

/**
 * 2つの列車IDが同じ物理的な電車を指すかチェック
 *
 * @param {string} id1 - 最初の列車ID (trip_id or train_number)
 * @param {string} id2 - 2番目の列車ID
 * @returns {boolean} 同じ電車を指す場合は true
 *
 * @example
 * isSameTrain("1:1111406H", "4200406H")  // → true (両方とも "406H")
 * isSameTrain("1:1111406H", "4201301G")  // → false
 */
export function isSameTrain(id1, id2) {
  const n1 = extractTrainNumber(id1);
  const n2 = extractTrainNumber(id2);
  return n1 === n2 && n1 !== "";
}
