(async function(){
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  const ctx = canvas.getContext('2d');
  try{
    const stream = await navigator.mediaDevices.getUserMedia({video:true});
    video.srcObject = stream;
  }catch(e){ console.error(e) }

  document.getElementById('captureBtn').addEventListener('click', async (e)=>{
    e.preventDefault();
    ctx.drawImage(video,0,0,canvas.width,canvas.height);
    const data = canvas.toDataURL('image/jpeg');
    const form = new FormData(document.getElementById('regForm'));
    const payload = { image: data, name: form.get('name'), class_id: form.get('class_id'), roll: form.get('roll') };
    const res = await fetch('/school/save_face', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const j = await res.json();
    document.getElementById('status').innerText = JSON.stringify(j);
  });
})();
